#!/usr/bin/env python3
"""Generate a flat, shadowless PBR base-color (albedo) with Z-Image Turbo (txt2img, clean stack).

Self-contained (own HTTP helpers) so the pbr-materials track is independent of the 2d track.
No ControlNet, no background removal — materials are opaque, full-frame. Prompt for flat even
diffuse lighting / no shadows so no directional lighting is baked into the albedo.
"""
import argparse
import time
import uuid
from pathlib import Path

import requests

UNET = "z_image_turbo_bf16.safetensors"
CLIP = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE = "ae.safetensors"


def build_txt2img_graph(prompt: str, seed: int, size: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 0]}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["4", 0], "shift": 3.0}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": size, "height": size, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                         "sampler_name": "res_multistep", "scheduler": "simple",
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["6", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def _queue(server, graph):
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def _wait(server, pid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{pid}", timeout=30).json()
        if pid in h:
            return h[pid]
        time.sleep(2)
    raise SystemExit("timed out")


def _download(server, hist, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for node in hist.get("outputs", {}).values():
        for im in node.get("images", []):
            r = requests.get(f"{server}/view", params={"filename": im["filename"],
                             "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")}, timeout=60)
            r.raise_for_status()
            p = out_dir / im["filename"]
            p.write_bytes(r.content)
            return p
    raise SystemExit("no image in history outputs")


def generate_albedo(server: str, prompt: str, seed: int, size: int, out_dir: Path, name: str) -> Path:
    server = server.rstrip("/")
    graph = build_txt2img_graph(prompt, seed, size, f"asset_harness/material_{name}")
    pid = _queue(server, graph)
    hist = _wait(server, pid)
    return _download(server, hist, out_dir)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--name", default="material")
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    p = generate_albedo(args.server, args.prompt, args.seed, args.size, Path(args.out), args.name)
    print("albedo ->", p)


if __name__ == "__main__":
    main()
