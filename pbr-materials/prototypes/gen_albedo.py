#!/usr/bin/env python3
"""Generate a flat, shadowless PBR base-color (albedo) with Z-Image Turbo (txt2img, clean stack).

Self-contained (own HTTP helpers) so the pbr-materials track is independent of the 2d track.
No ControlNet, no background removal — materials are opaque, full-frame. Prompt for flat even
diffuse lighting / no shadows so no directional lighting is baked into the albedo.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

import requests

CLIP = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE = "ae.safetensors"

# Model presets — kept in step with (but deliberately copied from) the 2d track's
# run_zimage_controlnet.py, per the track-independence convention this module documents above.
# Turbo→Base is a regime swap: distilled Turbo runs cfg 1 with a zeroed negative; Base is
# non-distilled and wants a real cfg, more steps, and an encoded negative prompt.
MODELS = {
    "turbo": {"unet": "z_image_turbo_bf16.safetensors", "steps": 8, "cfg": 1.0,
              "sampler": "res_multistep", "scheduler": "simple", "shift": 3.0, "zero_negative": True},
    "base": {"unet": "z_image_bf16.safetensors", "steps": 20, "cfg": 4.0,
             "sampler": "euler", "scheduler": "simple", "shift": 3.0, "zero_negative": False},
}
DEFAULT_NEGATIVE = (
    "blurry, low quality, low resolution, jpeg artifacts, watermark, signature, text, "
    "deformed, extra limbs, bad anatomy, cluttered background"
)

# Back-compat: preserve the module-level Turbo checkpoint name for any external reference.
UNET = MODELS["turbo"]["unet"]


def _negative_node(preset: dict, negative: str) -> dict:
    if preset["zero_negative"]:
        return {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    return {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 0]}}


def build_txt2img_graph(prompt: str, seed: int, size: int, prefix: str, model: str = "turbo",
                        negative: str = DEFAULT_NEGATIVE, steps: int | None = None,
                        cfg: float | None = None) -> dict:
    if model not in MODELS:
        raise SystemExit(f"unknown model {model!r}; valid: {', '.join(MODELS)}")
    preset = MODELS[model]
    steps = preset["steps"] if steps is None else steps
    cfg = preset["cfg"] if cfg is None else cfg
    return {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 0]}},
        "3": _negative_node(preset, negative),
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": preset["unet"], "weight_dtype": "default"}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["4", 0], "shift": preset["shift"]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": size, "height": size, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": preset["sampler"], "scheduler": preset["scheduler"],
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


def generate_albedo(server: str, prompt: str, seed: int, size: int, out_dir: Path, name: str,
                    model: str = "turbo", negative: str = DEFAULT_NEGATIVE,
                    steps: int | None = None, cfg: float | None = None) -> Path:
    server = server.rstrip("/")
    graph = build_txt2img_graph(prompt, seed, size, f"asset_harness/material_{name}",
                                model=model, negative=negative, steps=steps, cfg=cfg)
    preset = MODELS[model]
    ks = graph["8"]["inputs"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_run.json").write_text(json.dumps({
        "server": server, "seed": seed, "size": size, "name": name, "prompt": prompt,
        "model": model,
        "sampling": {"steps": ks["steps"], "cfg": ks["cfg"], "sampler": ks["sampler_name"],
                     "scheduler": ks["scheduler"], "shift": preset["shift"],
                     "negative": None if preset["zero_negative"] else negative},
        "models": {"unet": preset["unet"], "clip": CLIP, "vae": VAE},
    }, indent=2))
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
    ap.add_argument("--model", default="turbo", choices=sorted(MODELS),
                    help="Z-Image engine: turbo (fast, distilled, cfg1) or base (real cfg + negatives)")
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE,
                    help="negative prompt; used only by --model base (turbo zeroes the negative)")
    ap.add_argument("--cfg", type=float, default=None, help="override the preset cfg")
    ap.add_argument("--steps", type=int, default=None, help="override the preset step count")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    if args.negative != DEFAULT_NEGATIVE and MODELS[args.model]["zero_negative"]:
        print(f"note: --negative is ignored for --model {args.model} (its negative is zeroed)")
    p = generate_albedo(args.server, args.prompt, args.seed, args.size, Path(args.out), args.name,
                        model=args.model, negative=args.negative, steps=args.steps, cfg=args.cfg)
    print("albedo ->", p)


if __name__ == "__main__":
    main()
