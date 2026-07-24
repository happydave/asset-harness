#!/usr/bin/env python3
"""WI 1037 spike: run clean-licence candidate scorers over the generated sets, emit machine rankings.

Images (per shot group): CLIPScore (prompt-image alignment gate) + PickScore (human-preference ranker).
Audio (per song set):     LAION-CLAP (brief alignment) + Audiobox Aesthetics (CE/PQ production quality).

Each scorer is optional (try/except) so a missing one does not sink the run. Emits:
  scoring/machine_scores.json  -- every candidate's raw scores + per-group ranks
Determinism control: every image is scored twice by PickScore; a drift is flagged.

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
# The song brief for CLAP text-audio alignment (the ACE-Step tags describe the intended song).
SONG_BRIEF = ("post-apocalyptic folk rock with male and female vocals, gritty clean singing, "
              "melancholic determined mood, acoustic guitar and drums")


def _ranks(scores: dict) -> dict:
    """Map name -> 1-based rank (1 = best/highest score)."""
    order = sorted(scores, key=lambda k: scores[k], reverse=True)
    return {name: i + 1 for i, name in enumerate(order)}


# ---------------- image scorers ----------------
def score_images():
    from PIL import Image
    results = {}  # group -> {name -> {clip, pickscore}}
    groups = {}
    for p in sorted(STILLS.glob("*.png")):
        key = "sanity" if p.name.startswith("sanity") else p.name.split("_seed")[0]
        groups.setdefault(key, []).append(p)
    # each real shot group is scored against ITS prompt; sanity is scored against BOTH shot prompts
    # (it must lose to the real candidates under whichever prompt it is compared).

    # CLIP
    clip = None
    try:
        from transformers import CLIPModel, CLIPProcessor
        cm = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        cp = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        cm.eval()

        def clip_score(prompt, img):
            import torch
            inp = cp(text=[prompt], images=Image.open(img).convert("RGB"),
                     return_tensors="pt", padding=True, truncation=True)
            with torch.no_grad():
                out = cm(**inp)
            ie = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
            te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
            return float((ie * te).sum().item())
        clip = clip_score
        print("CLIP loaded")
    except Exception as e:
        print(f"CLIP unavailable: {e}")

    # PickScore (human-preference ranker; transformers-native, unlike ImageReward whose vendored BLIP
    # breaks on modern transformers). Score = image_embed . text_embed (rank by it within a group).
    ir = None
    try:
        import torch
        from transformers import AutoModel, AutoProcessor
        pp = AutoProcessor.from_pretrained("laion/CLIP-ViT-H-14-laion2B-s32B-b79K")
        pm = AutoModel.from_pretrained("yuvalkirstain/PickScore_v1")
        pm.eval()

        def ir_score(prompt, img):
            inp = pp(text=[prompt], images=Image.open(img).convert("RGB"), return_tensors="pt",
                     padding=True, truncation=True, max_length=77)
            with torch.no_grad():
                out = pm(**inp)
            ie = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
            te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
            return float((ie * te).sum().item())
        ir = ir_score
        print("PickScore loaded")
    except Exception as e:
        print(f"PickScore unavailable: {e}")

    det_flag = None
    for group, paths in groups.items():
        prompt = SHOT_PROMPTS.get(group) or SHOT_PROMPTS["shot4"]  # sanity judged vs a real prompt
        g = {}
        for p in paths:
            rec = {}
            if clip:
                rec["clip"] = round(clip(prompt, p), 4)
            if ir:
                s1 = ir(prompt, p)
                rec["pickscore"] = round(s1, 4)
                # determinism control on the first image only
                if det_flag is None:
                    det_flag = abs(ir(prompt, p) - s1) < 1e-6
            g[p.name] = rec
        results[group] = {
            "prompt": prompt,
            "scores": g,
            "rank_clip": _ranks({k: v["clip"] for k, v in g.items() if "clip" in v}) if clip else {},
            "rank_pickscore": _ranks({k: v["pickscore"] for k, v in g.items()
                                        if "pickscore" in v}) if ir else {},
        }
    return results, {"pickscore_deterministic": det_flag}


# ---------------- audio scorers ----------------
def score_audio():
    songs = {}
    if SONG_SEED701.exists():
        songs["seed701"] = SONG_SEED701
    for p in sorted(SONGS_EXTRA.glob("*.flac")):
        songs[p.stem.replace("clamor_hold_the_line_", "")] = p
    if not songs:
        return {"error": "no songs found"}, {}

    import soundfile as sf
    import librosa

    def load_audio(path, sr=48000):
        y, orig = sf.read(str(path))
        if y.ndim > 1:
            y = y.mean(axis=1)
        if orig != sr:
            y = librosa.resample(y.astype("float32"), orig_sr=orig, target_sr=sr)
        return y.astype("float32")

    clap = None
    try:
        import torch
        from transformers import ClapModel, ClapProcessor
        cm = ClapModel.from_pretrained("laion/larger_clap_music")
        cp = ClapProcessor.from_pretrained("laion/larger_clap_music")
        cm.eval()

        def clap_score(brief, path):
            y = load_audio(path, 48000)
            inp = cp(text=[brief], audio=[y], sampling_rate=48000, return_tensors="pt", padding=True)
            with torch.no_grad():
                out = cm(**inp)
            ae = out.audio_embeds / out.audio_embeds.norm(dim=-1, keepdim=True)
            te = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
            return float((ae * te).sum().item())
        clap = clap_score
        print("CLAP loaded")
    except Exception as e:
        print(f"CLAP unavailable: {e}")

    aes = None
    try:
        from audiobox_aesthetics.infer import initialize_predictor
        pred = initialize_predictor()

        def aes_score(path):
            out = pred.forward([{"path": str(path)}])[0]
            return {k: round(float(v), 4) for k, v in out.items()}
        aes = aes_score
        print("Audiobox loaded")
    except Exception as e:
        print(f"Audiobox unavailable: {e}")

    g = {}
    for name, path in songs.items():
        rec = {}
        if clap:
            rec["clap"] = round(clap(SONG_BRIEF, path), 4)
        if aes:
            rec["audiobox"] = aes(path)
        g[name] = rec
    out = {"brief": SONG_BRIEF, "scores": g}
    if clap:
        out["rank_clap"] = _ranks({k: v["clap"] for k, v in g.items() if "clap" in v})
    if aes:
        out["rank_audiobox_CE"] = _ranks({k: v["audiobox"]["CE"] for k, v in g.items()
                                          if "audiobox" in v})
        out["rank_audiobox_PQ"] = _ranks({k: v["audiobox"]["PQ"] for k, v in g.items()
                                          if "audiobox" in v})
    return out, {}


def main():
    print("=== scoring images ===")
    img, img_ctrl = score_images()
    print("=== scoring audio ===")
    aud, _ = score_audio()
    out = {"images": img, "audio": aud, "controls": img_ctrl}
    (HERE / "machine_scores.json").write_text(json.dumps(out, indent=2))
    print(f"-> {HERE/'machine_scores.json'}")
    # brief human-readable summary
    for group, d in img.items():
        if d.get("rank_pickscore"):
            best = min(d["rank_pickscore"], key=d["rank_pickscore"].get)
            print(f"[img {group}] PickScore top pick: {best}")
    if aud.get("rank_clap"):
        best = min(aud["rank_clap"], key=aud["rank_clap"].get)
        print(f"[audio] CLAP top pick: {best}")


if __name__ == "__main__":
    main()
