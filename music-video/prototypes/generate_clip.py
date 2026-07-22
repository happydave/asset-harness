#!/usr/bin/env python3
"""Wan2.2 image-to-video on ComfyUI (`ai2`) — the music-video track's motion shots.

Graph transcribed from the shipped ComfyUI "Image to Video (Wan 2.2)" blueprint. That blueprint is
*subgraph-wrapped*: a shallow read shows one opaque node, and the real chain lives in
`definitions.subgraphs`. Expanded, it is:

  CLIPLoader(umt5_xxl_fp8_e4m3fn_scaled, type=wan) -> CLIPTextEncode x2 (positive / negative)
  UNETLoader(wan2.2_i2v_high_noise_14B_fp8_scaled) -> [LoraLoaderModelOnly] -> ModelSamplingSD3(5)
  UNETLoader(wan2.2_i2v_low_noise_14B_fp8_scaled)  -> [LoraLoaderModelOnly] -> ModelSamplingSD3(5)
  LoadImage -> WanImageToVideo(width, height, frames, batch 1) -> LATENT
  KSamplerAdvanced(high, steps 0..k)  -> KSamplerAdvanced(low, steps k..N) -> VAEDecode(wan_2.1_vae)
  -> CreateVideo(16 fps) -> SaveVideo

Two regimes, both shipped in the blueprint:

  --lora    4-step lightx2v distillation LoRAs, 4 steps, cfg 1   (fast; the blueprint's own note:
            "will result in the loss of video dynamics, but it will reduce the generation time")
  --no-lora plain fp8_scaled, 20 steps, cfg 3.5                  (slow; full motion)

The blueprint's embedded benchmark (RTX 4090D 24GB, 640x640): ~536s without the LoRA, ~97s first /
~71s subsequent with it. Those are CUDA figures; measuring the ROCm gfx1201 numbers is the point.

LICENCE CHAIN (the repo rule is that an output's effective licence is the MOST RESTRICTIVE link, so
the LoRAs count, not just the base model):
  Wan2.2-I2V-A14B base ................ Apache-2.0   (HF model card + LICENSE.txt)
  lightx2v 4-step LoRAs (Seko-V1) ..... Apache-2.0   (lightx2v/Wan2.2-Lightning frontmatter;
                                                      ModelTC/LightX2V code likewise Apache-2.0)
  Comfy-Org/Wan_2.2_ComfyUI_Repackaged  no licence asserted -- a metadata omission, not a
                                        restriction; the LoRA file is a byte-identical rename of
                                        the Apache-2.0 lightx2v weight.
  => Effective output licence: Apache-2.0.

See ../license-lane.md before writing a motion prompt: no franchise, character or living-artist
names (exposure 4).
"""
from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

import requests

HIGH_UNET = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
LOW_UNET = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
HIGH_LORA = "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
LOW_LORA = "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "wan_2.1_vae.safetensors"

# The blueprint's stock negative prompt, kept verbatim: it is the Wan authors' own, tuned for this
# model, and swapping it would confound a cost measurement with a prompt change.
NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
            "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
            "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
            "杂乱的背景，三条腿，背景人很多，倒着走")


def build_graph(image_name: str, prompt: str, *, width: int, height: int, frames: int,
                fps: int, seed: int, use_lora: bool, steps: int, cfg: float,
                prefix: str) -> dict:
    """Two model branches (high-noise, low-noise), optionally each through its speed LoRA."""
    g: dict = {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan", "device": "default"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": prompt}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": NEGATIVE}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_name, "upload": "image"}},
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": HIGH_UNET, "weight_dtype": "default"}},
        "20": {"class_type": "UNETLoader", "inputs": {"unet_name": LOW_UNET, "weight_dtype": "default"}},
    }

    if use_lora:
        g["11"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["10", 0], "lora_name": HIGH_LORA, "strength_model": 1.0}}
        g["21"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["20", 0], "lora_name": LOW_LORA, "strength_model": 1.0}}
        high_src, low_src = ["11", 0], ["21", 0]
    else:
        high_src, low_src = ["10", 0], ["20", 0]

    g["12"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": high_src, "shift": 5.0}}
    g["22"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": low_src, "shift": 5.0}}

    g["30"] = {"class_type": "WanImageToVideo",
               "inputs": {"positive": ["3", 0], "negative": ["4", 0], "vae": ["2", 0],
                          "start_image": ["5", 0], "width": width, "height": height,
                          "length": frames, "batch_size": 1}}

    # The two-stage split: the high-noise model runs the first half of the schedule and hands the
    # partially-denoised latent to the low-noise model. `return_with_leftover_noise` on stage 1 and
    # `add_noise=disable` on stage 2 are what make the handoff work.
    split = steps // 2
    g["40"] = {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["12", 0], "add_noise": "enable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["30", 0], "negative": ["30", 1], "latent_image": ["30", 2],
                          "start_at_step": 0, "end_at_step": split,
                          "return_with_leftover_noise": "enable"}}
    g["41"] = {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["22", 0], "add_noise": "disable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["30", 0], "negative": ["30", 1], "latent_image": ["40", 0],
                          "start_at_step": split, "end_at_step": steps,
                          "return_with_leftover_noise": "disable"}}

    g["50"] = {"class_type": "VAEDecode", "inputs": {"samples": ["41", 0], "vae": ["2", 0]}}
    g["51"] = {"class_type": "CreateVideo", "inputs": {"images": ["50", 0], "fps": fps}}
    g["52"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["51", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def upload_image(server: str, path: Path) -> str:
    with path.open("rb") as fh:
        r = requests.post(f"{server}/upload/image",
                          files={"image": (path.name, fh, "image/png")},
                          data={"overwrite": "true"}, timeout=120)
    r.raise_for_status()
    j = r.json()
    return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]


def queue(server: str, graph: dict) -> str:
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex},
                      timeout=60)
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
        time.sleep(5)
    raise SystemExit(f"timed out after {timeout:.0f}s — report this as the measurement "
                     f"('longer than {timeout:.0f}s'), it still answers the sizing question")


def download(server: str, hist: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    for node in hist.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            for item in node.get(key, []):
                r = requests.get(f"{server}/view",
                                 params={"filename": item["filename"],
                                         "subfolder": item.get("subfolder", ""),
                                         "type": item.get("type", "output")}, timeout=600)
                r.raise_for_status()
                p = out.with_suffix(Path(item["filename"]).suffix or ".mp4")
                p.write_bytes(r.content)
                return p
    raise SystemExit(f"no video in history outputs; keys were "
                     f"{[k for n in hist.get('outputs', {}).values() for k in n]}")


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True, help="input still (i2v start frame)")
    ap.add_argument("--prompt", required=True, help="motion prompt — see ../license-lane.md exposure 4")
    ap.add_argument("--out", default=None, help="output path stem")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=640)
    ap.add_argument("--frames", type=int, default=81, help="81 @ 16fps = ~5.06s")
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--seed", type=int, default=901)
    ap.add_argument("--no-lora", dest="lora", action="store_false",
                    help="skip the 4-step speed LoRAs: slower, but keeps motion dynamics")
    ap.add_argument("--steps", type=int, default=None, help="default 4 with LoRA, 20 without")
    ap.add_argument("--cfg", type=float, default=None, help="default 1.0 with LoRA, 3.5 without")
    ap.add_argument("--timeout", type=float, default=3600)
    args = ap.parse_args()

    steps = args.steps if args.steps is not None else (4 if args.lora else 20)
    cfg = args.cfg if args.cfg is not None else (1.0 if args.lora else 3.5)
    server = args.server.rstrip("/")
    tag = "lora4" if args.lora else "nolora"
    out = Path(args.out) if args.out else here / "outputs" / f"clip_{tag}_s{args.seed}"

    name = upload_image(server, Path(args.image))
    graph = build_graph(name, args.prompt, width=args.width, height=args.height,
                        frames=args.frames, fps=args.fps, seed=args.seed,
                        use_lora=args.lora, steps=steps, cfg=cfg,
                        prefix=f"asset_harness/mv_clip_{tag}")

    print(f"regime={tag} steps={steps} cfg={cfg} {args.width}x{args.height} "
          f"{args.frames}f@{args.fps}fps (~{args.frames / args.fps:.2f}s) seed={args.seed}")
    t0 = time.time()
    hist = wait(server, queue(server, graph), args.timeout)
    path = download(server, hist, out)
    elapsed = time.time() - t0
    clip_s = args.frames / args.fps
    print(f"-> {path}")
    print(f"   WALL-CLOCK {elapsed:.0f}s for a {clip_s:.2f}s clip  "
          f"({elapsed / clip_s:.0f}x realtime)")
    print(f"   a 3-minute song at ~{clip_s:.0f}s/shot = ~{round(180 / clip_s)} clips "
          f"= ~{elapsed * (180 / clip_s) / 3600:.1f}h")


if __name__ == "__main__":
    main()
