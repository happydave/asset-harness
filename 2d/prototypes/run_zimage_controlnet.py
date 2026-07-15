#!/usr/bin/env python3
"""Asset-harness 2D prototype: Z-Image Turbo + Fun ControlNet (Canny) + alpha cutout.

Clean-license stack only (all Apache/MIT): Z-Image Turbo, Z-Image Fun ControlNet Union,
core Canny, native BiRefNet matting background removal. No LoRAs, no finetunes.

Pipeline:
  control image -> scale 1024 -> Canny -> QwenImageDiffsynthControlnet(patch=Z-Image cnet)
  Z-Image Turbo (8 steps, cfg 1, res_multistep/simple, AuraFlow shift 3)
  -> VAEDecode -> RemoveBackground(BiRefNet-HR-matting) -> JoinImageWithAlpha -> PNG (RGBA)

Builds the ComfyUI API graph, uploads the control image, queues it on the server,
polls history, and downloads the RGBA sprite + the opaque render + the Canny map.
Stdlib + requests only.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

import requests

# --- installed artifact names on the target server (verified via /object_info) ---
# Shared across every Z-Image preset (same text encoder / VAE / ControlNet / matte model):
CLIP = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE = "ae.safetensors"
CNET_PATCH = "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors"
BG_MODEL = "BiRefNet-HR-matting.safetensors"

# Model presets. Turbo→Base is a *regime* swap, not just a checkpoint swap: the distilled Turbo
# runs at cfg 1 with the negative zeroed out, while Base is non-distilled and wants a real cfg, more
# steps, and a genuinely encoded negative prompt. Each preset therefore carries the whole regime.
MODELS = {
    # Reproduces the historical behaviour exactly (do not change — see plan invariant I1).
    "turbo": {"unet": "z_image_turbo_bf16.safetensors", "steps": 8, "cfg": 1.0,
              "sampler": "res_multistep", "scheduler": "simple", "shift": 3.0, "zero_negative": True},
    # Non-distilled: real negatives + cfg. Defaults are sane starting points, override with --cfg/--steps.
    "base": {"unet": "z_image_bf16.safetensors", "steps": 20, "cfg": 4.0,
             "sampler": "euler", "scheduler": "simple", "shift": 3.0, "zero_negative": False},
    # Z-Anime: Apache-2.0 anime full fine-tune of Z-Image Base — same non-distilled regime as base.
    "zanime": {"unet": "z-anime-base-bf16.safetensors", "steps": 20, "cfg": 4.0,
               "sampler": "euler", "scheduler": "simple", "shift": 3.0, "zero_negative": False},
}
# Used only when a preset does not zero the negative (i.e. Base). Generic quality guard.
DEFAULT_NEGATIVE = (
    "blurry, low quality, low resolution, jpeg artifacts, watermark, signature, text, "
    "deformed, extra limbs, bad anatomy, cluttered background"
)

# Back-compat: some callers still reference the module-level Turbo checkpoint name.
UNET = MODELS["turbo"]["unet"]

# Canonical house style — the project's STYLE ANCHOR. Prepended to every subject so a whole
# fleet stays visually coherent (used in lieu of LoRA/IPAdapter, which we deliberately avoid).
STYLE = (
    "top-down orthographic game sprite, industrial used-future space vessel, "
    "weathered painted steel hull, gunmetal grey with rust-orange hazard accents, "
    "soft even studio lighting, clean readable silhouette, centered, "
    "isolated on a plain solid white background, crisp detailed concept art"
)
DEFAULT_SUBJECT = (
    "a heavy cargo hauler with armored greebled hull, side cargo pods, "
    "and three engine nozzles with a faint glow"
)


def compose(subject: str, style: str = STYLE) -> str:
    return f"{style}, {subject}"


DEFAULT_PROMPT = compose(DEFAULT_SUBJECT)


def upload_image(server: str, path: Path) -> str:
    with path.open("rb") as f:
        r = requests.post(
            f"{server}/upload/image",
            files={"image": (path.name, f, "image/png")},
            data={"overwrite": "true"},
            timeout=30,
        )
    r.raise_for_status()
    j = r.json()
    name = j["name"]
    if j.get("subfolder"):
        name = f"{j['subfolder']}/{name}"
    return name


def _negative_node(preset: dict, negative: str) -> dict:
    """Node '3', the KSampler negative source. Turbo zeroes it (distilled, cfg 1); Base encodes a
    real negative prompt. Keeping the id stable at '3' means the Turbo graph is byte-identical to the
    historical one (plan invariant I1 / behaviour B2)."""
    if preset["zero_negative"]:
        return {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    return {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 0]}}


def build_graph(control_name: str, prompt: str, seed: int, strength: float,
                prefix: str = "asset_harness/hauler", model: str = "turbo",
                negative: str = DEFAULT_NEGATIVE, steps: int | None = None,
                cfg: float | None = None) -> dict:
    if model not in MODELS:
        raise SystemExit(f"unknown model {model!r}; valid: {', '.join(MODELS)}")
    preset = MODELS[model]
    steps = preset["steps"] if steps is None else steps
    cfg = preset["cfg"] if cfg is None else cfg
    return {
        "1": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 0]}},
        "3": _negative_node(preset, negative),
        "4": {"class_type": "UNETLoader",
              "inputs": {"unet_name": preset["unet"], "weight_dtype": "default"}},
        "5": {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": ["4", 0], "shift": preset["shift"]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "7": {"class_type": "ModelPatchLoader", "inputs": {"name": CNET_PATCH}},
        "8": {"class_type": "LoadImage", "inputs": {"image": control_name}},
        "9": {"class_type": "ImageScaleToMaxDimension",
              "inputs": {"image": ["8", 0], "upscale_method": "lanczos", "largest_size": 1024}},
        "10": {"class_type": "Canny",
               "inputs": {"image": ["9", 0], "low_threshold": 0.1, "high_threshold": 0.32}},
        "11": {"class_type": "QwenImageDiffsynthControlnet",
               "inputs": {"model": ["5", 0], "model_patch": ["7", 0], "vae": ["6", 0],
                          "image": ["10", 0], "strength": strength}},
        "12": {"class_type": "GetImageSize", "inputs": {"image": ["9", 0]}},
        "13": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": ["12", 0], "height": ["12", 1], "batch_size": 1}},
        "14": {"class_type": "KSampler",
               "inputs": {"model": ["11", 0], "seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": preset["sampler"], "scheduler": preset["scheduler"],
                          "positive": ["2", 0], "negative": ["3", 0],
                          "latent_image": ["13", 0], "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["6", 0]}},
        # alpha tail
        "16": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": BG_MODEL}},
        "17": {"class_type": "RemoveBackground", "inputs": {"image": ["15", 0], "bg_removal_model": ["16", 0]}},
        # RemoveBackground's mask marks background as foreground-of-mask; invert so the
        # SHIP becomes opaque and the background transparent.
        "22": {"class_type": "InvertMask", "inputs": {"mask": ["17", 0]}},
        "18": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["15", 0], "alpha": ["22", 0]}},
        # outputs: RGBA sprite, opaque render, canny map (for inspection)
        "19": {"class_type": "SaveImage", "inputs": {"images": ["18", 0], "filename_prefix": f"{prefix}_rgba"}},
        "20": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": f"{prefix}_opaque"}},
        "21": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": f"{prefix}_canny"}},
    }


def queue(server: str, graph: dict, client_id: str) -> str:
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": client_id}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def wait(server: str, prompt_id: str, timeout: int = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{prompt_id}", timeout=30).json()
        if prompt_id in h:
            return h[prompt_id]
        time.sleep(2)
    raise SystemExit("timed out waiting for generation")


def download(server: str, hist: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for im in node_out.get("images", []):
            params = {"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")}
            r = requests.get(f"{server}/view", params=params, timeout=60)
            r.raise_for_status()
            p = out_dir / im["filename"]
            p.write_bytes(r.content)
            saved.append(p)
    return saved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--control", default="inputs/hauler_primitive.png")
    ap.add_argument("--prompt", default=None, help="full prompt override; else style+subject")
    ap.add_argument("--style", default=STYLE)
    ap.add_argument("--subject", default=DEFAULT_SUBJECT)
    ap.add_argument("--name", default="hauler", help="output basename / atlas frame key")
    ap.add_argument("--seed", type=int, default=729703840979498)
    ap.add_argument("--strength", type=float, default=0.85)
    ap.add_argument("--model", default="turbo", choices=sorted(MODELS),
                    help="Z-Image engine: turbo (fast, distilled, cfg1) or base (real cfg + negatives)")
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE,
                    help="negative prompt; used only by --model base (turbo zeroes the negative)")
    ap.add_argument("--cfg", type=float, default=None, help="override the preset cfg")
    ap.add_argument("--steps", type=int, default=None, help="override the preset step count")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()

    server = args.server.rstrip("/")
    client_id = uuid.uuid4().hex
    out_dir = Path(args.out)
    prompt = args.prompt or compose(args.subject, args.style)
    if args.negative != DEFAULT_NEGATIVE and MODELS[args.model]["zero_negative"]:
        print(f"note: --negative is ignored for --model {args.model} (its negative is zeroed)")

    print(f"uploading {args.control} ...")
    control_name = upload_image(server, Path(args.control))
    graph = build_graph(control_name, prompt, args.seed, args.strength,
                        prefix=f"asset_harness/{args.name}", model=args.model,
                        negative=args.negative, steps=args.steps, cfg=args.cfg)

    preset = MODELS[args.model]
    ks = graph["14"]["inputs"]
    # persist the exact graph + provenance next to outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_graph.json").write_text(json.dumps(graph, indent=2))
    (out_dir / "last_run.json").write_text(json.dumps({
        "server": server, "control": control_name, "seed": args.seed,
        "strength": args.strength, "prompt": prompt,
        "model": args.model,
        "sampling": {"steps": ks["steps"], "cfg": ks["cfg"], "sampler": ks["sampler_name"],
                     "scheduler": ks["scheduler"], "shift": preset["shift"],
                     "negative": None if preset["zero_negative"] else args.negative},
        "models": {"unet": preset["unet"], "clip": CLIP, "vae": VAE,
                   "controlnet": CNET_PATCH, "bg": BG_MODEL},
    }, indent=2))

    print("queueing ...")
    pid = queue(server, graph, client_id)
    print(f"prompt_id={pid}; waiting ...")
    hist = wait(server, pid)
    status = hist.get("status", {})
    print("status:", status.get("status_str"), "completed:", status.get("completed"))
    saved = download(server, hist, out_dir)
    print(f"downloaded {len(saved)} file(s):")
    for p in saved:
        print("  ", p)


if __name__ == "__main__":
    main()
