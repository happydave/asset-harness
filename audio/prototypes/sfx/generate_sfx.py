#!/usr/bin/env python3
"""Generate a game SFX set with Stable Audio 3 Medium Base (local, clean-licensed) on ComfyUI.

Graph mirrors the shipped ComfyUI "Stable Audio 3 Medium Base" blueprint, minus its optional
LLM prompt-expander chain (we write prompts directly in the blueprint's SFX style instead):

  CheckpointLoaderSimple(stable_audio_3_medium_base) -> MODEL + VAE
  CLIPLoader(t5gemma_b_b_ul2, type=stable_audio)      -> CLIP (feeds both text encoders)
  CLIPTextEncode(prompt) / CLIPTextEncode("")         -> positive / negative CONDITIONING
  EmptyLatentAudio(seconds)                            -> LATENT
  KSampler(50, cfg 7, lcm, simple)                     -> LATENT   (blueprint defaults)
  VAEDecodeAudio -> SaveAudio (FLAC, 48 kHz)

Outputs land in ./outputs/ as <name>.flac for the ffmpeg post step (optimize_audio.py).

Licensing: Stable Audio 3 = Stability AI Community License (free commercial <$1M org revenue;
owns outputs); training data fully licensed (AudioSparx + Freesound CC). Stack bundles the
T5Gemma encoder under the Gemma Terms of Use. See ../../discover.md.
"""
import argparse
import time
import uuid
from pathlib import Path

import requests

CKPT = "stable_audio_3_medium_base.safetensors"
CLIP = "t5gemma_b_b_ul2.safetensors"
CLIP_TYPE = "stable_audio"

# First SFX set for DWA: a one-shot click, a thruster loop bed, an impact one-shot, an ambient hum.
# Prompts follow the blueprint's SFX system-prompt style: dense, physical, spatial. `loop`/`lufs`
# drive the post step (optimize_audio.py); `seconds` sets the generated length.
SFX = [
    {"name": "ui_click", "seconds": 1.5, "seed": 101, "loop": False, "lufs": -16,
     "prompt": "Soft futuristic user-interface button click, a single short crisp digital tick "
               "with a subtle synthetic resonance, clean and dry, very close perspective."},
    {"name": "thruster_loop", "seconds": 6.0, "seed": 102, "loop": True, "lufs": -18,
     "prompt": "Spaceship engine thruster burn, steady low-frequency rumble layered with a "
               "continuous hiss of high-pressure plasma, smooth and sustained, no transients, "
               "interior-exterior hybrid perspective."},
    # Start/stop transients share the loop's engine language (low rumble + plasma hiss) for
    # cohesion, and layer over the loop bed in-engine. `thruster_start` must end hot (post with
    # --fade 0) so it blends into the loop; `thruster_stop` keeps its natural decay.
    {"name": "thruster_start", "seconds": 2.0, "seed": 105, "loop": False, "lufs": -16,
     "prompt": "Spaceship engine ignition, a pressurized whoosh and deep low-end thump spooling up "
               "into a steady low-frequency rumble with high-pressure plasma hiss, building to a "
               "sustained burn, close exterior perspective."},
    {"name": "thruster_stop", "seconds": 2.0, "seed": 106, "loop": False, "lufs": -16,
     "prompt": "Spaceship engine shutdown, a steady low-frequency rumble and plasma hiss cutting "
               "out into a descending hiss and a soft mechanical decay, dying away, close exterior "
               "perspective."},
    {"name": "impact_metal", "seconds": 2.0, "seed": 103, "loop": False, "lufs": -14,
     "prompt": "Heavy metal-on-metal collision impact, deep bass thud with a sharp metallic clang "
               "and a short ringing decay, dry, close perspective."},
    {"name": "station_hum", "seconds": 12.0, "seed": 104, "loop": True, "lufs": -22,
     "prompt": "Space station interior ambience, low steady mechanical drone with a subtle "
               "electrical buzz and distant air-handling, smooth and continuous, spacious."},
]


def build_graph(prompt: str, seconds: float, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "5": {"class_type": "EmptyLatentAudio", "inputs": {"seconds": seconds, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": 50, "cfg": 7.0,
                         "sampler_name": "lcm", "scheduler": "simple",
                         "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "denoise": 1.0}},
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudio", "inputs": {"audio": ["7", 0], "filename_prefix": prefix}},
    }


def _queue(server, graph):
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def _wait(server, pid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{pid}", timeout=30).json()
        if pid in h:
            return h[pid]
        time.sleep(2)
    raise SystemExit("timed out")


def _download(server, hist, out_dir, name):
    out_dir.mkdir(parents=True, exist_ok=True)
    for node in hist.get("outputs", {}).values():
        for au in node.get("audio", []):
            r = requests.get(f"{server}/view", params={"filename": au["filename"],
                             "subfolder": au.get("subfolder", ""), "type": au.get("type", "output")}, timeout=120)
            r.raise_for_status()
            ext = Path(au["filename"]).suffix or ".flac"
            p = out_dir / f"{name}{ext}"
            p.write_bytes(r.content)
            return p
    raise SystemExit(f"no audio in history outputs for {name}")


def generate(server: str, item: dict, out_dir: Path) -> Path:
    server = server.rstrip("/")
    graph = build_graph(item["prompt"], item["seconds"], item["seed"], f"asset_harness/sfx_{item['name']}")
    pid = _queue(server, graph)
    hist = _wait(server, pid)
    return _download(server, hist, out_dir, item["name"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--out", default=str(Path(__file__).parent / "outputs"))
    ap.add_argument("--only", help="generate only this SFX name")
    args = ap.parse_args()
    out_dir = Path(args.out)
    for item in SFX:
        if args.only and item["name"] != args.only:
            continue
        p = generate(args.server, item, out_dir)
        print(f"generated {item['name']} ({item['seconds']}s) -> {p}")


if __name__ == "__main__":
    main()
