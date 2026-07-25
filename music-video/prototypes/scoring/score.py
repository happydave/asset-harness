#!/usr/bin/env python3
"""WI 1045: candidate scorers, corrected. Emits machine rankings for the retained WI 1037 set.

WI 1037's harness had two defects that meant the scorers were not shown what the owner judged. Both are
fixed here, and the old behaviour is retained SIDE BY SIDE so the correction is measurable rather than
asserted (scoring/compare_rankings.py reads both):

  1. CLAP scored a RANDOM 10 s crop of a 75 s song. `laion/larger_clap_music`'s feature extractor
     defaults to max_length_s=10, truncation='rand_trunc'; the harness never overrode it. Measured: the
     same song scored six times spread 0.0179, against a 0.0169 spread across all four songs -- the
     noise exceeded the signal, so the ranking was a coin flip. FIX: cut the track into fixed 10 s
     windows and score each. A window at or under the model's own length has nothing to truncate, so
     rand_trunc becomes a no-op and the result is deterministic AND covers the whole song.

  2. The image scorers saw the MIDDLE SQUARE of a 16:9 frame. Both CLIP processors resize the short
     edge to 224 then centre-crop 224x224, discarding the left and right thirds -- ~44% of a 1280x720
     still, on prompts that all ask for a "cinematic wide establishing shot". FIX: pre-shape the frame
     ourselves into a square before the processor sees it, so its centre-crop is a no-op. Three
     treatments are scored per candidate:
       centrecrop -- the old behaviour, kept for comparison
       letterbox  -- whole frame on a square canvas; nothing discarded, but adds bars the scorers'
                     training distribution never contained
       multicrop  -- left/centre/right square crops, averaged; nothing discarded, no bars, but the
                     centre is weighted by overlap
     Neither fix is obviously "correct" for models trained on centre-cropped natural images, which is
     why both are measured instead of one being assumed.

  3. Audiobox Aesthetics never ran: its torchcodec reader links against libnvrtc.so.13 (CUDA), absent
     on this box. FIX: hand it a decoded tensor instead of a path -- its resampler accepts
     {"path": wav_tensor, "sample_rate": sr} and bypasses the file reader entirely. It windows the
     whole track internally.

  4. WI 1037 ran a determinism control on the IMAGE path only, and it passed -- which is exactly the
     shape of evidence that makes an untested second path feel covered. Every scorer is now controlled.

Run with the track-local scoring venv:  scoring/.venv/bin/python scoring/score.py
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent
SPIKE = PROTO / "outputs" / "spike1037"
STILLS = SPIKE / "stills"
SONGS_EXTRA = SPIKE / "songs"
SONG_SEED701 = PROTO / "outputs" / "clamor_hold_the_line_seed701.flac"
OUT = HERE / "machine_scores_v2.json"  # v1 (machine_scores.json) is retained evidence; never overwrite

STYLE = ("painterly tabletop RPG concept art, dramatic volumetric light, warm lantern glow against "
         "cool blue shadows, cinematic wide establishing shot, richly detailed, muted desaturated "
         "palette, moody atmospheric")
SHOT_PROMPTS = {
    "shot4": ("two survivors inside a dark ruined building, one holding up a burning red flare that "
              "casts dramatic light, a menacing shadow looming in a broken stairwell behind them, "
              "tense, " + STYLE),
    "shot7": ("dawn breaking over a ruined city as silhouetted survivors walk away toward a fortified "
              "colony gate glowing with warm safe light, hope and resolution, wide cinematic vista, "
              + STYLE),
}
SONG_BRIEF = ("post-apocalyptic folk rock with male and female vocals, gritty clean singing, "
              "melancholic determined mood, acoustic guitar and drums")

TREATMENTS = ("centrecrop", "letterbox", "multicrop")
CLAP_SR = 48000
CLAP_WINDOW_S = 10  # the model's own max_length_s; windows at/under it make rand_trunc a no-op


def _ranks(scores: dict) -> dict:
    """name -> 1-based rank (1 = best/highest score)."""
    order = sorted(scores, key=lambda k: scores[k], reverse=True)
    return {name: i + 1 for i, name in enumerate(order)}


# ---------------- frame treatments ----------------
def frame_variants(path):
    """A 16:9 still -> the square inputs each treatment feeds the scorer.

    Returned images are already square, so the processor's resize+centre-crop cannot discard anything.
    """
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    side = min(w, h)
    centre = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    canvas = Image.new("RGB", (max(w, h), max(w, h)), (0, 0, 0))
    canvas.paste(im, ((max(w, h) - w) // 2, (max(w, h) - h) // 2))
    crops = [im.crop((x, (h - side) // 2, x + side, (h + side) // 2))
             for x in (0, (w - side) // 2, w - side)]  # left, centre, right
    return {"centrecrop": [centre], "letterbox": [canvas], "multicrop": crops}


# ---------------- image scorers ----------------
def _cosine_scorer(model, processor):
    """text-image cosine over a list of already-square images, averaged. Deterministic."""
    import torch

    def score(prompt, images):
        vals = []
        for im in images:
            inp = processor(text=[prompt], images=im, return_tensors="pt",
                            padding=True, truncation=True, max_length=77)
            with torch.no_grad():
                out = model(**inp)
            ie = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
            te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
            vals.append(float((ie * te).sum().item()))
        return sum(vals) / len(vals)
    return score


def score_images(controls):
    results, groups = {}, {}
    # The off-brief sanity image is scored against a REAL shot's prompt and ranked INSIDE that group --
    # in a group of its own it is trivially 1st of 1, which tests nothing. (v1 emitted it as its own
    # group; the numbers were still comparable, but "garbage ranks last" was never a within-group result.)
    ref = sorted({p.name.split("_seed")[0] for p in STILLS.glob("*.png")
                  if not p.name.startswith("sanity")})
    ref = ref[0] if ref else "shot4"
    for p in sorted(STILLS.glob("*.png")):
        groups.setdefault(ref if p.name.startswith("sanity") else p.name.split("_seed")[0], []).append(p)

    scorers = {}
    try:
        from transformers import CLIPModel, CLIPProcessor
        m = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
        scorers["clip"] = _cosine_scorer(m, CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"))
        print("CLIP loaded")
    except Exception as e:
        print(f"CLIP unavailable: {e}")
    try:
        from transformers import AutoModel, AutoProcessor
        m = AutoModel.from_pretrained("yuvalkirstain/PickScore_v1").eval()
        scorers["pickscore"] = _cosine_scorer(
            m, AutoProcessor.from_pretrained("laion/CLIP-ViT-H-14-laion2B-s32B-b79K"))
        print("PickScore loaded")
    except Exception as e:
        print(f"PickScore unavailable: {e}")

    first = True
    for group, paths in groups.items():
        prompt = SHOT_PROMPTS.get(group) or SHOT_PROMPTS["shot4"]
        g = {}
        for p in sorted(paths):
            variants = frame_variants(p)
            rec = {}
            for sname, fn in scorers.items():
                for t in TREATMENTS:
                    try:
                        rec[f"{sname}_{t}"] = round(fn(prompt, variants[t]), 4)
                    except Exception as e:
                        print(f"  {sname}/{t} failed on {p.name}: {str(e)[:70]}")
                if first:  # determinism control: every scorer, not just one
                    try:
                        again = round(fn(prompt, variants["centrecrop"]), 4)
                        controls[f"{sname}_deterministic"] = (again == rec.get(f"{sname}_centrecrop"))
                    except Exception:
                        controls[f"{sname}_deterministic"] = None
            first = False
            g[p.name] = rec
        entry = {"prompt": prompt, "scores": g}
        for sname in scorers:
            for t in TREATMENTS:
                col = f"{sname}_{t}"
                vals = {k: v[col] for k, v in g.items() if col in v}
                if vals:
                    entry[f"rank_{col}"] = _ranks(vals)
        results[group] = entry
    return results


# ---------------- audio scorers ----------------
def _load_mono(path, sr=CLAP_SR):
    import librosa
    import soundfile as sf
    y, orig = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if orig != sr:
        y = librosa.resample(np.ascontiguousarray(y), orig_sr=orig, target_sr=sr)
    return np.ascontiguousarray(y.astype("float32")), orig


def default_songs():
    songs = {}
    if SONG_SEED701.exists():
        songs["seed701"] = SONG_SEED701
    for p in sorted(SONGS_EXTRA.glob("*.flac")):
        songs[p.stem.replace("clamor_hold_the_line_", "")] = p
    return songs


def score_audio(controls, songs=None):
    """Score a {name: path} mapping; defaults to the retained WI 1037 song set."""
    songs = default_songs() if songs is None else songs
    if not songs:
        return {"error": "no songs found"}

    clap = None
    try:
        import torch
        from transformers import ClapModel, ClapProcessor
        cm = ClapModel.from_pretrained("laion/larger_clap_music").eval()
        cp = ClapProcessor.from_pretrained("laion/larger_clap_music")

        def clap_windows(brief, y):
            """Score every 10 s window across the whole track. Deterministic by construction: a window
            no longer than the model's own max_length_s gives rand_trunc nothing to truncate."""
            n = CLAP_WINDOW_S * CLAP_SR
            wins = [y[i:i + n] for i in range(0, max(len(y), 1), n)]
            wins = [w for w in wins if len(w) >= CLAP_SR]  # drop a <1 s tail; too short to characterise
            vals = []
            for w in wins:
                inp = cp(text=[brief], audio=[w], sampling_rate=CLAP_SR,
                         return_tensors="pt", padding=True)
                with torch.no_grad():
                    out = cm(**inp)
                ae = out.audio_embeds / out.audio_embeds.norm(dim=-1, keepdim=True)
                te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
                vals.append(round(float((ae * te).sum().item()), 5))
            return vals
        clap = clap_windows
        print("CLAP loaded")
    except Exception as e:
        print(f"CLAP unavailable: {e}")

    aes = None
    try:
        import torch
        from audiobox_aesthetics.infer import initialize_predictor
        pred = initialize_predictor()

        def aes_score(y, sr):
            # Bypass its torchcodec file reader (links libnvrtc.so.13, absent here) by passing a
            # decoded tensor; the predictor windows the whole track internally.
            wav = torch.from_numpy(np.ascontiguousarray(y)).unsqueeze(0)
            out = pred.forward([{"path": wav, "sample_rate": sr}])[0]
            return {k: round(float(v), 4) for k, v in out.items()}
        aes = aes_score
        print("Audiobox loaded")
    except Exception as e:
        print(f"Audiobox unavailable: {e}")

    g, first = {}, True
    for name, path in songs.items():
        y, _orig_sr = _load_mono(path)
        rec = {}
        if clap:
            try:
                wins = clap(SONG_BRIEF, y)
                rec["clap_windows"] = wins
                rec["clap"] = round(sum(wins) / len(wins), 5)
                rec["clap_min"], rec["clap_max"] = min(wins), max(wins)
                if first:
                    controls["clap_deterministic"] = (
                        round(sum(clap(SONG_BRIEF, y)) / len(wins), 5) == rec["clap"])
            except Exception as e:
                print(f"  clap failed on {name}: {str(e)[:70]}")
                controls.setdefault("clap_deterministic", None)
        if aes:
            try:
                rec["audiobox"] = aes(y, CLAP_SR)
                if first:
                    controls["audiobox_deterministic"] = (aes(y, CLAP_SR) == rec["audiobox"])
            except Exception as e:
                print(f"  audiobox failed on {name}: {str(e)[:70]}")
                controls.setdefault("audiobox_deterministic", None)
        first = False
        g[name] = rec

    out = {"brief": SONG_BRIEF, "aggregation": f"mean of non-overlapping {CLAP_WINDOW_S}s windows",
           "scores": g}
    if any("clap" in v for v in g.values()):
        out["rank_clap"] = _ranks({k: v["clap"] for k, v in g.items() if "clap" in v})
    for axis in ("CE", "CU", "PC", "PQ"):
        vals = {k: v["audiobox"][axis] for k, v in g.items() if "audiobox" in v}
        if vals:
            out[f"rank_audiobox_{axis}"] = _ranks(vals)
    return out


def main():
    controls = {}
    print("=== scoring images ===")
    img = score_images(controls)
    print("=== scoring audio ===")
    aud = score_audio(controls)
    OUT.write_text(json.dumps({"images": img, "audio": aud, "controls": controls}, indent=2))
    print(f"-> {OUT}")

    print("\ndeterminism controls (every scorer must be True):")
    for k, v in sorted(controls.items()):
        print(f"  {k:26s} {v}")
    if any(v is not True for v in controls.values()):
        print("  !! a scorer is non-deterministic or unverified -- harness failure, not a result")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
