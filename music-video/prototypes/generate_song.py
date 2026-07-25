#!/usr/bin/env python3
"""Generate a song **with sung lyrics** using ACE-Step 1.5 on ComfyUI (`ai2`).

This is the `music-video` track's counterpart to the `audio` track's
`prototypes/music/generate_music.py`, which is instrumental-only by policy. The graph is the same;
the difference is that the `lyrics` field is populated.

  UNETLoader(<checkpoint>) -> ModelSamplingAuraFlow(shift 3) -> MODEL
  DualCLIPLoader(qwen_0.6b_ace15 + qwen_4b_ace15, type=ace) -> CLIP
  TextEncodeAceStepAudio1.5(tags, LYRICS, bpm, duration, key, ...) -> positive
  ConditioningZeroOut(positive) -> negative
  EmptyAceStep1.5LatentAudio(seconds) -> LATENT
  KSampler(euler, simple, <steps>, <cfg>) -> VAEDecodeAudio(ace_1.5_vae) -> SaveAudio (FLAC)

CHECKPOINTS (WI 1043) — the arms differ ONLY by the UNET and its own sampler regime; encoders, VAE,
shift and every TextEncodeAceStepAudio1.5 parameter are shared, so an A/B varies one thing. Sampler
regimes are ComfyUI's shipped template defaults for each checkpoint; `turbo` is distilled and runs at
cfg 1.0, which disables classifier-free guidance -> one model evaluation per step instead of two.

LICENSE LANE — read ../license-lane.md before changing the lyrics or tags. In short:
  * Lyrics here are authored original for this project. Never paste existing lyrics.
  * Never name an artist in `tags` ("in the style of ..."), and never steer at a named song.
  * Vocal output is permitted for standalone media artifacts only, never as a shipped in-game
    audio asset — that remains the `audio` track's instrumental-only rule.
  * Record the checks in the findings entry.

Candidates: pass several seeds (`--seeds 701,702,703`) to get the 3-5 variants the pick gate wants.
Same tags + same lyrics + different noise; ACE-Step's own "retake lottery" in its simplest form.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import comfy_client

CLIP1 = "qwen_0.6b_ace15.safetensors"
CLIP2 = "qwen_4b_ace15.safetensors"
CLIP_TYPE = "ace"
VAE = "ace_1.5_vae.safetensors"
SHIFT = 3.0

CHECKPOINTS = {
    # non-distilled; 40/5.0. Retained for comparison / fallback.
    "base": {"unet": "acestep_v1.5_xl_base_bf16.safetensors", "steps": 40, "cfg": 5.0},
    # distilled; ComfyUI's audio_ace_step1_5_xl_turbo template settings. Same size class as base
    # (9.97 GB BF16, identical tensor topology), so base-vs-turbo isolates the distillation.
    "turbo": {"unet": "acestep_v1.5_xl_turbo_bf16.safetensors", "steps": 8, "cfg": 1.0},
}
# WI 1043: turbo won two blind owner listening tests on vocal quality (a clean 4-2 arm sweep in the
# level-matched round 2; the owner's "tinny" vocals were exactly the base tracks) and is ~1.8x faster.
DEFAULT_CHECKPOINT = "turbo"

# WI 1046: every generated song is trimmed to this true-peak ceiling (pure gain, no limiting) so no
# candidate ships "hot". Turbo's transients land over 0 dBTP; -1 dBTP is EBU R128 delivery practice.
CEILING_DBTP = -1.0

# --- the test subject -------------------------------------------------------------------------
#
# Themed on Clamor (co-op turn-based zombie survival; small bands scavenging for a colony back
# home) so the artifact is reusable by WI 1004's lobby loop rather than a throwaway.
#
# Structural tags are load-bearing beyond the audio: [verse]/[chorus] are the join key between a
# lyric line and a shot, and survive even when precise timestamps do not.

LYRICS = """[verse]
Six of us went out at first light
Counting every step and every round
The colony is waiting on the far side
Of a city that has forgotten how to make a sound

[chorus]
Hold the line, hold the line
Take what we can carry, leave the rest behind
One more street, one more night
We are going home, we are going home tonight

[verse]
She has got the map and I have got the last flare
Something in the stairwell heard us come
Do not you run, do not you make a sound out there
Count it down and take them one by one

[chorus]
Hold the line, hold the line
Take what we can carry, leave the rest behind
One more street, one more night
We are going home, we are going home tonight
"""

SONG = {
    "name": "clamor_hold_the_line",
    "seconds": 75.0,
    "bpm": 96,
    "key": "D minor",
    # Genre / instrumentation / mood / vocal character. No artist names, no song names.
    "tags": ("post-apocalyptic folk rock, male and female vocals, gritty clean vocal, "
             "acoustic guitar, driving drums, bass, mournful strings, minor key, "
             "anthemic chorus, weary, defiant, cinematic"),
    "lyrics": LYRICS,
}


def build_graph(t: dict, seed: int, prefix: str, *, checkpoint: str = DEFAULT_CHECKPOINT) -> dict:
    """Graph for one song. `checkpoint` selects a CHECKPOINTS arm (UNET + its sampler regime).

    Keyword-only with a default so existing positional callers keep the base recipe unchanged.
    """
    ck = CHECKPOINTS[checkpoint]
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": ck["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": SHIFT}},
        "3": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": CLIP1, "clip_name2": CLIP2, "type": CLIP_TYPE, "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "5": {"class_type": "TextEncodeAceStepAudio1.5",
              "inputs": {"clip": ["3", 0], "tags": t["tags"], "lyrics": t["lyrics"], "seed": seed,
                         "bpm": t["bpm"], "duration": t["seconds"], "timesignature": "4",
                         "language": "en", "keyscale": t["key"], "generate_audio_codes": True,
                         "cfg_scale": 2.0, "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": t["seconds"], "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "seed": seed, "steps": ck["steps"], "cfg": ck["cfg"],
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveAudio", "inputs": {"audio": ["9", 0], "filename_prefix": prefix}},
    }


def _postprocess(path: Path, *, ceiling: float | None) -> dict:
    """Apply the delivery ceiling and run the truncation check on a freshly generated song.

    A save-time step (not baked into the ComfyUI graph) so it is deterministic, inspectable, and equally
    applicable to any audio the track produces. Runs in the scoring venv as a SUBPROCESS: the DSP needs
    numpy/scipy/soundfile, while this generator runs under plain python3 (requests only). If the venv or
    ffmpeg is missing, degrade to a no-op with a warning rather than failing the generation.
    """
    import json
    import subprocess

    scoring = Path(__file__).parent / "scoring"
    venv_py = scoring / ".venv" / "bin" / "python"
    if not venv_py.exists():
        print(f"  (postprocess skipped: scoring venv not found at {venv_py})")
        return {"skipped": True}
    cmd = [str(venv_py), str(scoring / "postprocess.py"), str(path)]
    cmd += ["--no-ceiling"] if ceiling is None else ["--ceiling", str(ceiling)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(r.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        detail = getattr(e, "stderr", str(e))
        print(f"  (postprocess failed, delivering raw file: {str(detail)[:120]})")
        return {"skipped": True, "error": True}


def generate(server: str, t: dict, seed: int, out_dir: Path,
             backstop: float | None = None, checkpoint: str = DEFAULT_CHECKPOINT,
             ceiling: float | None = CEILING_DBTP) -> tuple[Path, float, dict]:
    server = server.rstrip("/")
    name = f"{t['name']}_seed{seed}"
    graph = build_graph(t, seed, f"asset_harness/mv_{name}", checkpoint=checkpoint)
    t0 = time.time()
    path = comfy_client.run_job(server, graph, out_dir / name, kinds=("audio",),
                                backstop=backstop, label=name)[0]
    elapsed = time.time() - t0
    return path, elapsed, _postprocess(path, ceiling=ceiling)


def write_lyric_sheet(t: dict, out_dir: Path) -> Path:
    """The authored lyric sheet is an INPUT to alignment, never re-derived from the audio."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{t['name']}.lyrics.txt"
    p.write_text(t["lyrics"])
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--out", default=str(Path(__file__).parent / "outputs"))
    ap.add_argument("--seeds", default="701",
                    help="comma-separated seeds; several = several candidates for the pick gate")
    ap.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT, choices=sorted(CHECKPOINTS),
                    help="which CHECKPOINTS arm to generate with (UNET + its sampler regime)")
    ap.add_argument("--no-ceiling", action="store_true",
                    help=f"skip the {CEILING_DBTP} dBTP delivery ceiling (default: apply it)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    sheet = write_lyric_sheet(SONG, out_dir)
    print(f"lyric sheet -> {sheet}")
    ck = CHECKPOINTS[args.checkpoint]
    ceiling = None if args.no_ceiling else CEILING_DBTP
    print(f"checkpoint {args.checkpoint}: {ck['unet']} steps={ck['steps']} cfg={ck['cfg']}"
          f"   ceiling={'off' if ceiling is None else f'{ceiling} dBTP'}")

    for seed in [int(s) for s in args.seeds.split(",") if s.strip()]:
        path, elapsed, qc = generate(args.server, SONG, seed, out_dir,
                                     checkpoint=args.checkpoint, ceiling=ceiling)
        c = qc.get("ceiling")
        if c and c["changed"]:
            cmsg = f"  peak {c['before_dbtp']:+.2f}->{c['after_dbtp']:+.2f} dBTP"
        elif "true_peak_dbtp" in qc:
            cmsg = f"  peak {qc['true_peak_dbtp']:+.2f} dBTP (under ceiling)"
        else:
            cmsg = ""
        print(f"seed {seed}: {SONG['seconds']}s @ bpm {SONG['bpm']} {SONG['key']} "
              f"-> {path}  ({elapsed:.0f}s wall-clock){cmsg}")
        if qc.get("truncated"):
            print(f"  !! WARNING seed {seed} looks TRUNCATED (cut off mid-phrase, not resolved) — "
                  f"consider re-rolling this seed; the arrangement did not fit {SONG['seconds']}s")


if __name__ == "__main__":
    main()
