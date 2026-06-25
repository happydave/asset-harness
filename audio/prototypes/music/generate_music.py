#!/usr/bin/env python3
"""Generate instrumental ambient music beds with ACE-Step 1.5 (MIT weights, local) on ComfyUI.

Graph from the shipped ComfyUI "Text to Audio (ACE-Step 1.5)" blueprint, adapted to the **base**
model on `ai2` (`acestep_v1.5_xl_base_bf16` — the turbo checkpoint isn't installed, so we use real
sampler settings, not the turbo 8-step/cfg-1 defaults):

  UNETLoader(acestep_v1.5_xl_base_bf16) -> ModelSamplingAuraFlow(shift 3) -> MODEL
  DualCLIPLoader(qwen_0.6b_ace15 + qwen_4b_ace15, type=ace) -> CLIP
  TextEncodeAceStepAudio1.5(tags, lyrics="", bpm, duration, key, ...) -> positive
  ConditioningZeroOut(positive) -> negative
  EmptyAceStep1.5LatentAudio(seconds) -> LATENT
  KSampler(euler, simple) -> VAEDecodeAudio(ace_1.5_vae) -> SaveAudio (FLAC)

INSTRUMENTAL ONLY — lyrics are always empty (vocal style-mimicry risk regardless of the MIT
weights). Beds are looped by the shared post step (optimize_audio.py --loop).

Licensing: ACE-Step 1.5 weights MIT; training data licensed + royalty-free + synthetic (vendor
claim). See ../../discover.md.
"""
import argparse
import time
import uuid
from pathlib import Path

import requests

UNET = "acestep_v1.5_xl_base_bf16.safetensors"
CLIP1 = "qwen_0.6b_ace15.safetensors"
CLIP2 = "qwen_4b_ace15.safetensors"
CLIP_TYPE = "ace"
VAE = "ace_1.5_vae.safetensors"
STEPS = 40
CFG = 5.0

# Instrumental ambient beds for the games. `tags` is ACE-Step's comma-separated descriptor list
# (genre / instruments / mood); lyrics stay empty. Beds are looped in post.
TRACKS = [
    {"name": "ambient_deep_space", "seconds": 45.0, "seed": 501, "bpm": 60, "key": "A minor", "lufs": -23,
     "tags": "ambient, dark ambient, space, instrumental, slow evolving synth pads, deep drones, "
             "distant shimmer, sub bass, no drums, no vocals, cinematic, vast, lonely"},
    {"name": "ambient_exploration", "seconds": 45.0, "seed": 502, "bpm": 70, "key": "C major", "lufs": -23,
     "tags": "ambient, instrumental, calm, wondrous, warm synth pads, soft slow arpeggio, gentle "
             "bells, airy texture, no drums, no vocals, hopeful, spacious, cinematic"},
    {"name": "ambient_tense", "seconds": 45.0, "seed": 503, "bpm": 80, "key": "D minor", "lufs": -22,
     "tags": "dark ambient, instrumental, suspenseful, ominous low drone, subtle pulsing bass, "
             "dissonant pads, industrial tension, no melody, no vocals, brooding, cinematic"},
]


def build_graph(t: dict, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "3": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": CLIP1, "clip_name2": CLIP2, "type": CLIP_TYPE, "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "5": {"class_type": "TextEncodeAceStepAudio1.5",
              "inputs": {"clip": ["3", 0], "tags": t["tags"], "lyrics": "", "seed": t["seed"],
                         "bpm": t["bpm"], "duration": t["seconds"], "timesignature": "4",
                         "language": "en", "keyscale": t["key"], "generate_audio_codes": True,
                         "cfg_scale": 2.0, "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": t["seconds"], "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "seed": t["seed"], "steps": STEPS, "cfg": CFG,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveAudio", "inputs": {"audio": ["9", 0], "filename_prefix": prefix}},
    }


def _queue(server, graph):
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def _wait(server, pid, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{pid}", timeout=30).json()
        if pid in h:
            return h[pid]
        time.sleep(3)
    raise SystemExit("timed out")


def _download(server, hist, out_dir, name):
    out_dir.mkdir(parents=True, exist_ok=True)
    for node in hist.get("outputs", {}).values():
        for au in node.get("audio", []):
            r = requests.get(f"{server}/view", params={"filename": au["filename"],
                             "subfolder": au.get("subfolder", ""), "type": au.get("type", "output")}, timeout=180)
            r.raise_for_status()
            ext = Path(au["filename"]).suffix or ".flac"
            p = out_dir / f"{name}{ext}"
            p.write_bytes(r.content)
            return p
    raise SystemExit(f"no audio in history outputs for {name}")


def generate(server: str, t: dict, out_dir: Path) -> Path:
    server = server.rstrip("/")
    graph = build_graph(t, f"asset_harness/music_{t['name']}")
    pid = _queue(server, graph)
    hist = _wait(server, pid)
    return _download(server, hist, out_dir, t["name"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--out", default=str(Path(__file__).parent / "outputs"))
    ap.add_argument("--only", help="generate only this track name")
    args = ap.parse_args()
    out_dir = Path(args.out)
    for t in TRACKS:
        if args.only and t["name"] != args.only:
            continue
        p = generate(args.server, t, out_dir)
        print(f"generated {t['name']} ({t['seconds']}s, bpm {t['bpm']}, {t['key']}) -> {p}")


if __name__ == "__main__":
    main()
