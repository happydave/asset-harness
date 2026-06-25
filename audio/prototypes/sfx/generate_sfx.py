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
    # Thruster set re-rolled (WI 630): the original "high-pressure plasma hiss" language read
    # as static. De-hissed to a deep tonal rocket engine + a negative prompt that rejects
    # broadband noise; fresh seeds. One shared engine vocabulary keeps the three cohesive.
    {"name": "thruster_loop", "seconds": 6.0, "seed": 412, "loop": True, "lufs": -18,
     "neg": "harsh hiss, white noise, static, crackle, distortion, fizz",
     "prompt": "Powerful spaceship rocket engine sustained burn, deep resonant low-frequency "
               "roar and thick warm sub-bass rumble, smooth full-bodied drone, steady and "
               "continuous, no hiss, no transients, no static."},
    # Start/stop share the loop's engine language and layer over the loop bed in-engine.
    # `thruster_start` ends hot (post --fade 0) to blend into the loop; `thruster_stop` decays.
    {"name": "thruster_start", "seconds": 2.0, "seed": 415, "loop": False, "lufs": -16,
     "neg": "harsh hiss, white noise, static, crackle, distortion, fizz",
     "prompt": "Powerful spaceship rocket engine ignition, a deep low-end thump and pressurized "
               "whoosh spooling up into a sustained resonant low-frequency roar, smooth and "
               "building, full-bodied, no hiss, no static."},
    {"name": "thruster_stop", "seconds": 2.0, "seed": 416, "loop": False, "lufs": -16,
     "neg": "harsh hiss, white noise, static, crackle, distortion, fizz",
     "prompt": "Powerful spaceship rocket engine shutdown, a deep low roar winding down through a "
               "descending pitch into a soft mechanical thud and silence, smooth spool-down, "
               "no hiss, no static."},
    {"name": "impact_metal", "seconds": 2.0, "seed": 103, "loop": False, "lufs": -14,
     "prompt": "Heavy metal-on-metal collision impact, deep bass thud with a sharp metallic clang "
               "and a short ringing decay, dry, close perspective."},
    {"name": "station_hum", "seconds": 12.0, "seed": 104, "loop": True, "lufs": -22,
     "prompt": "Space station interior ambience, low steady mechanical drone with a subtle "
               "electrical buzz and distant air-handling, smooth and continuous, spacious."},
]


def build_graph(prompt: str, seconds: float, seed: int, prefix: str, neg: str = "") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["2", 0]}},
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


def generate(server: str, item: dict, out_dir: Path, seed: int | None = None) -> Path:
    server = server.rstrip("/")
    graph = build_graph(item["prompt"], item["seconds"], seed if seed is not None else item["seed"],
                        f"asset_harness/sfx_{item['name']}", item.get("neg", ""))
    pid = _queue(server, graph)
    hist = _wait(server, pid)
    return _download(server, hist, out_dir, item["name"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--out", default=str(Path(__file__).parent / "outputs"))
    ap.add_argument("--only", help="generate only this SFX name")
    ap.add_argument("--seed", type=int, default=None, help="override seed (use with --only for re-rolls)")
    args = ap.parse_args()
    out_dir = Path(args.out)
    for item in SFX:
        if args.only and item["name"] != args.only:
            continue
        seed = args.seed if (args.only and args.seed is not None) else None
        p = generate(args.server, item, out_dir, seed)
        print(f"generated {item['name']} ({item['seconds']}s, seed={seed if seed is not None else item['seed']}) -> {p}")


if __name__ == "__main__":
    main()
