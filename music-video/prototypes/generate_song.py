#!/usr/bin/env python3
"""Generate a song **with sung lyrics** using ACE-Step 1.5 on ComfyUI (`ai2`).

This is the `music-video` track's counterpart to the `audio` track's
`prototypes/music/generate_music.py`, which is instrumental-only by policy. The graph is the same;
the difference is that the `lyrics` field is populated.

  UNETLoader(acestep_v1.5_xl_base_bf16) -> ModelSamplingAuraFlow(shift 3) -> MODEL
  DualCLIPLoader(qwen_0.6b_ace15 + qwen_4b_ace15, type=ace) -> CLIP
  TextEncodeAceStepAudio1.5(tags, LYRICS, bpm, duration, key, ...) -> positive
  ConditioningZeroOut(positive) -> negative
  EmptyAceStep1.5LatentAudio(seconds) -> LATENT
  KSampler(euler, simple, 40 steps, cfg 5) -> VAEDecodeAudio(ace_1.5_vae) -> SaveAudio (FLAC)

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

UNET = "acestep_v1.5_xl_base_bf16.safetensors"
CLIP1 = "qwen_0.6b_ace15.safetensors"
CLIP2 = "qwen_4b_ace15.safetensors"
CLIP_TYPE = "ace"
VAE = "ace_1.5_vae.safetensors"
STEPS = 40
CFG = 5.0

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


def build_graph(t: dict, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
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
              "inputs": {"model": ["2", 0], "seed": seed, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveAudio", "inputs": {"audio": ["9", 0], "filename_prefix": prefix}},
    }


def generate(server: str, t: dict, seed: int, out_dir: Path,
             backstop: float | None = None) -> tuple[Path, float]:
    server = server.rstrip("/")
    name = f"{t['name']}_seed{seed}"
    graph = build_graph(t, seed, f"asset_harness/mv_{name}")
    t0 = time.time()
    path = comfy_client.run_job(server, graph, out_dir / name, kinds=("audio",),
                                backstop=backstop, label=name)[0]
    return path, time.time() - t0


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
    args = ap.parse_args()

    out_dir = Path(args.out)
    sheet = write_lyric_sheet(SONG, out_dir)
    print(f"lyric sheet -> {sheet}")

    for seed in [int(s) for s in args.seeds.split(",") if s.strip()]:
        path, elapsed = generate(args.server, SONG, seed, out_dir)
        print(f"seed {seed}: {SONG['seconds']}s @ bpm {SONG['bpm']} {SONG['key']} "
              f"-> {path}  ({elapsed:.0f}s wall-clock)")


if __name__ == "__main__":
    main()
