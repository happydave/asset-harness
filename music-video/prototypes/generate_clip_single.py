#!/usr/bin/env python3
"""Wan2.2 i2v — SINGLE-STAGE variant. ABANDONED 2026-07-28; kept as a record of the experiment.

DO NOT USE FOR DELIVERY. Use `generate_clip.py --fp16` (two-stage) — see
`skills/prompting-wan-i2v/SKILL.md` for the working recipe.

Why it was written (2026-07-27, clamor-motion session). The archie-night session measured a 5 s fp8
clip spending ~99% of its wall-clock swapping the two 14 GB checkpoints in and out of a 34 GB card
(~10 s of actual compute in 17+ min) and proposed running a single expert to avoid the swap. This
variant does that: ONE 14 GB checkpoint + its matching lightx2v 4-step LoRA over the whole 4-step
schedule, ~20 GB resident, no swap.

Why it was abandoned. It is fast, but the clips are wrong — figures pop in, scenes morph, night drifts
to day. Wan2.2 is a MoE that needs BOTH experts: high-noise carries structure and motion at high noise,
low-noise carries detail at low noise. Running one expert across the entire schedule is off-distribution,
and no prompt or seed rescues it.

What replaced it. ai2's saved `wan2.2-test` workflow — the two-stage MoE done properly: fp16
checkpoints, both lightx2v LoRAs, high-noise for sampler steps 0->2 handing its latent to low-noise for
steps 2->4. That splits the schedule so only one model is resident at a time (one swap per clip, not one
per step), which is what actually made two-stage affordable: ~6-10 min/clip, and coherent. The VRAM
thrash archie-night hit was the fp8 both-resident path, not two-stage as such. `generate_clip.py`
already builds this graph and already had the `--fp16` flag; the fix was to use it.

  --model low   (default)  low-noise expert — cleaner frames, gentler motion
  --model high             high-noise expert — more motion dynamics, rougher frames

    python3 generate_clip_single.py --image still.png --prompt "..." --model high --out clip
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import comfy_client
from generate_clip import HIGH_UNET, LOW_UNET, HIGH_LORA, LOW_LORA, CLIP, VAE, NEGATIVE, upload_image


def build_graph_single(image_name: str, prompt: str, *, width: int, height: int, frames: int,
                       fps: int, seed: int, model: str, steps: int, cfg: float, prefix: str,
                       use_lora: bool = True, sampler: str = "euler", scheduler: str = "simple",
                       shift: float = 5.0) -> dict:
    unet = LOW_UNET if model == "low" else HIGH_UNET
    lora = LOW_LORA if model == "low" else HIGH_LORA
    g: dict = {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan", "device": "default"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": prompt}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": NEGATIVE}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_name, "upload": "image"}},
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
    }
    if use_lora:
        g["11"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["10", 0], "lora_name": lora, "strength_model": 1.0}}
        src = ["11", 0]
    else:
        src = ["10", 0]
    g["12"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": src, "shift": shift}}
    g["30"] = {"class_type": "WanImageToVideo",
               "inputs": {"positive": ["3", 0], "negative": ["4", 0], "vae": ["2", 0],
                          "start_image": ["5", 0], "width": width, "height": height,
                          "length": frames, "batch_size": 1}}
    # Single sampler across the whole schedule (no high->low handoff).
    g["40"] = {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["12", 0], "add_noise": "enable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler,
                          "positive": ["30", 0], "negative": ["30", 1], "latent_image": ["30", 2],
                          "start_at_step": 0, "end_at_step": steps,
                          "return_with_leftover_noise": "disable"}}
    g["50"] = {"class_type": "VAEDecode", "inputs": {"samples": ["40", 0], "vae": ["2", 0]}}
    g["51"] = {"class_type": "CreateVideo", "inputs": {"images": ["50", 0], "fps": fps}}
    g["52"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["51", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", choices=("low", "high"), default="low")
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--frames", type=int, default=81, help="81 @ 16fps = ~5.06s")
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--seed", type=int, default=901)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--no-lora", dest="lora", action="store_false")
    ap.add_argument("--sampler", default="euler")
    ap.add_argument("--scheduler", default="simple")
    ap.add_argument("--shift", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=None)
    args = ap.parse_args()

    server = args.server.rstrip("/")
    tag = f"single_{args.model}_s{args.seed}"
    out = Path(args.out) if args.out else here / "outputs" / f"clip_{tag}"

    name = upload_image(server, Path(args.image))
    graph = build_graph_single(name, args.prompt, width=args.width, height=args.height,
                               frames=args.frames, fps=args.fps, seed=args.seed, model=args.model,
                               steps=args.steps, cfg=args.cfg, use_lora=args.lora,
                               prefix=f"asset_harness/mv_{tag}",
                               sampler=args.sampler, scheduler=args.scheduler, shift=args.shift)
    print(f"single-stage model={args.model} steps={args.steps} cfg={args.cfg} "
          f"{args.width}x{args.height} {args.frames}f@{args.fps}fps "
          f"(~{args.frames / args.fps:.2f}s) seed={args.seed}")
    t0 = time.time()
    path = comfy_client.run_job(server, graph, out, kinds=("videos", "gifs", "images"),
                                backstop=args.timeout, label=tag)[0]
    elapsed = time.time() - t0
    clip_s = args.frames / args.fps
    print(f"-> {path}")
    print(f"   WALL-CLOCK {elapsed:.0f}s for a {clip_s:.2f}s clip ({elapsed / clip_s:.0f}x realtime)")


if __name__ == "__main__":
    main()
