#!/usr/bin/env python3
"""Music-video track: opaque Z-Image text-to-image stills (i2v seed frames).

The 2D track's `run_zimage_controlnet.py` produces *matted RGBA sprites* via a ControlNet + BiRefNet
tail — exactly the alpha input that made Wan invent a background and hallucinate title text (WI 1002
F-5). This is the stripped, opaque-only sibling: plain text-to-image, no ControlNet, no matte, RGB out
at an arbitrary resolution. Its output is a full-scene still to hand straight to `generate_clip.py`.

Graph (node ids kept small; learned from run_zimage_controlnet.py, verified via /object_info):
  CLIPLoader(qwen_3_4b, lumina2) -> CLIPTextEncode(pos) / CLIPTextEncode(neg)
  UNETLoader(z_image_bf16 | z-anime-base-bf16) -> ModelSamplingAuraFlow(shift 3)
  EmptySD3LatentImage(w,h,1) -> KSampler(euler/simple, cfg, steps) -> VAEDecode(ae) -> SaveImage (RGB)

Non-distilled ("base"/"zanime") regime only: real cfg + a genuinely encoded negative. Turbo (cfg 1,
zeroed negative) is available but base gives better storytelling stills. Stdlib + requests only.

LICENCE: Z-Image (Tongyi) weights + qwen_3_4b encoder + ae VAE are the clean-lane 2D stack already
vetted for asset-harness (Apache/MIT). Prompt hygiene per ../license-lane.md (no franchise/artist names).
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import requests

CLIP = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE = "ae.safetensors"

MODELS = {
    "base": {"unet": "z_image_bf16.safetensors", "steps": 20, "cfg": 4.0,
             "sampler": "euler", "scheduler": "simple", "shift": 3.0},
    "zanime": {"unet": "z-anime-base-bf16.safetensors", "steps": 20, "cfg": 4.0,
               "sampler": "euler", "scheduler": "simple", "shift": 3.0},
}
# Quality guard for full-scene stills. Deliberately DROPS "cluttered background"/"isolated" — an
# establishing shot WANTS a rich background (planreview N-2). Keep it about defects and text.
DEFAULT_NEGATIVE = ("blurry, low quality, low resolution, jpeg artifacts, watermark, signature, "
                    "text, caption, title, subtitle, letters, ui, hud, frame border, "
                    "deformed, extra limbs, bad anatomy")


def build_graph(prompt: str, negative: str, *, width: int, height: int, seed: int,
                model: str, steps: int, cfg: float, prefix: str) -> dict:
    preset = MODELS[model]
    return {
        "1": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 0]}},
        "4": {"class_type": "UNETLoader",
              "inputs": {"unet_name": preset["unet"], "weight_dtype": "default"}},
        "5": {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": ["4", 0], "shift": preset["shift"]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "13": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": width, "height": height, "batch_size": 1}},
        "14": {"class_type": "KSampler",
               "inputs": {"model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": preset["sampler"], "scheduler": preset["scheduler"],
                          "positive": ["2", 0], "negative": ["3", 0],
                          "latent_image": ["13", 0], "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["6", 0]}},
        "20": {"class_type": "SaveImage",
               "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }


def queue(server: str, graph: dict) -> str:
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex},
                      timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def wait(server: str, pid: str, timeout: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(f"execution failed:\n{st}")
            return h[pid]
        time.sleep(3)
    raise SystemExit(f"timed out after {timeout:.0f}s")


def download(server: str, hist: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    for node in hist.get("outputs", {}).values():
        for item in node.get("images", []):
            r = requests.get(f"{server}/view",
                             params={"filename": item["filename"],
                                     "subfolder": item.get("subfolder", ""),
                                     "type": item.get("type", "output")}, timeout=120)
            r.raise_for_status()
            p = out.with_suffix(Path(item["filename"]).suffix or ".png")
            p.write_bytes(r.content)
            return p
    raise SystemExit("no image in history outputs")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--prompt", required=True, help="full positive prompt (subject + style)")
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True, help="output path stem")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", default="base", choices=sorted(MODELS))
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--timeout", type=float, default=600)
    args = ap.parse_args()

    preset = MODELS[args.model]
    steps = args.steps if args.steps is not None else preset["steps"]
    cfg = args.cfg if args.cfg is not None else preset["cfg"]
    server = args.server.rstrip("/")

    graph = build_graph(args.prompt, args.negative, width=args.width, height=args.height,
                        seed=args.seed, model=args.model, steps=steps, cfg=cfg,
                        prefix=f"asset_harness/mv_still_{args.model}")
    print(f"model={args.model} {args.width}x{args.height} steps={steps} cfg={cfg} seed={args.seed}")
    t0 = time.time()
    hist = wait(server, queue(server, graph), args.timeout)
    out = Path(args.out)
    path = download(server, hist, out)
    out.with_suffix(".run.json").write_text(json.dumps(
        {"prompt": args.prompt, "negative": args.negative, "width": args.width,
         "height": args.height, "seed": args.seed, "model": args.model, "steps": steps,
         "cfg": cfg}, indent=2))
    print(f"-> {path}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
