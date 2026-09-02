#!/usr/bin/env python3
"""Generate small symbolic RGBA icons (Slack-emoji targets) with Z-Image + BiRefNet.

The graph is txt2img joined to the alpha tail: no ControlNet. An emoji has no posed structure to
control — the subject is a single centred symbol — so the ControlNet path in
`run_zimage_controlnet.py` has nothing to steer, and Z-Image `base` cannot use it anyway (WI 924).

  CLIPTextEncode -> KSampler (Z-Image base) -> VAEDecode
                 -> RemoveBackground (BiRefNet) -> InvertMask -> JoinImageWithAlpha -> RGBA PNG

`base`, not `turbo`: this driver's job is VARIETY across seeds, and per `skills/prompting-z-image`
Turbo ignores negatives and shows almost no seed-to-seed variation.

Emits one RGBA PNG per candidate plus a per-candidate recipe JSON carrying the full prompt, seed,
sampler settings, model artifacts and the exact submitted graph — everything needed to replay it.
The opaque render is kept alongside so a bad matte is diagnosable rather than merely observed.

Clean-licence stack only (Apache-2.0 / MIT): Z-Image, BiRefNet-HR-matting. No LoRAs, no finetunes.

Stdlib + requests only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

import comfy_client

# --- installed artifact names on the target server (shared with the other 2d/pbr generators) ---
CLIP = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE = "ae.safetensors"
BG_MODEL = "BiRefNet-HR-matting.safetensors"

MODELS = {
    "base": {"unet": "z_image_bf16.safetensors", "steps": 20, "cfg": 4.0,
             "sampler": "euler", "scheduler": "simple", "shift": 3.0, "zero_negative": False},
    "zanime": {"unet": "z-anime-base-bf16.safetensors", "steps": 20, "cfg": 4.0,
               "sampler": "euler", "scheduler": "simple", "shift": 3.0, "zero_negative": False},
    # Speed fallback only. Turbo ignores the negative and barely varies with seed, which costs this
    # driver the one thing it is for.
    "turbo": {"unet": "z_image_turbo_bf16.safetensors", "steps": 8, "cfg": 1.0,
              "sampler": "res_multistep", "scheduler": "simple", "shift": 3.0, "zero_negative": True},
}

# The emoji style anchor. Two of its clauses are load-bearing for the MATTE, not for the look, and
# both were established by measurement rather than assumed (see
# ../findings/2026-09-01-world-of-magic-emoji.md):
#
#  1. The subject must be SMALL IN A WHITE FRAME. Asking for a "flat vector icon" alone yields
#     full-bleed artwork with no background at all, and BiRefNet then returns an empty mask —
#     there is nothing to separate. "a small ... icon, centered on a large plain white background,
#     generous empty white space around it" is the wording that actually produces a matte.
#  2. The subject must be SATURATED. A pale or white-filled subject on a white background is
#     unmattable: the matte keeps only the dark outlines and the fill goes transparent.
#
# The remaining clauses serve small-size legibility: one subject, a bold closed silhouette, thick
# outline, few internal details.
STYLE = (
    "a small flat vector icon, centered on a large plain white background, "
    "generous empty white space around it, thick dark outline, "
    "bold saturated colors, strong high contrast, minimal internal detail, one single subject"
)

# Negatives guard the failure modes that specifically ruin an emoji: incidental lettering (which
# degrades to noise at display size), fine detail (which disappears entirely), and the pale/white
# subject fill that defeats the matte.
NEGATIVE = (
    "text, letters, words, caption, title, watermark, signature, logo, "
    "thin delicate lines, fine intricate detail, busy cluttered composition, "
    "photorealistic, blurry, low contrast, pale washed out colors, white fill, "
    "drop shadow, full-bleed background, multiple separate objects"
)

# Concept directions: distinct READINGS of "we live in a world of magic" — the sentiment of something
# working impossibly well, the future having arrived. Not restyles of one idea.
#
# Prompt hygiene (repo hard gate, music-video/license-lane.md): no franchise, character, or
# named-work references. The stock cultural images of "magic" are mostly franchise wizards, so these
# directions deliberately reach for generic objects (hat, wand, hand, screen, circuit) instead.
# Each subject names its own strong colours: a pale subject cannot be matted (see STYLE note 2).
DIRECTIONS = {
    "hat-on-laptop": (
        "a deep blue pointed wizard hat covered in gold stars, resting on top of a dark grey "
        "open laptop computer, a few gold sparkles rising from the screen"
    ),
    "hand-sparkles": (
        "a bright blue glowing screen with a dark silhouetted hand in front of it, fingers spread, "
        "trailing a curve of gold sparkles"
    ),
    "hat-and-wand": (
        "a glossy black top hat tipped on its side with a black wand and a burst of gold stars "
        "spilling out of it"
    ),
    "glowing-object": (
        "a red coffee mug ringed by a bright gold halo of light, orange beams and small gold stars "
        "radiating outward from it"
    ),
    "circuit-bloom": (
        "a dark green circuit board chip with gold traces, blooming into a spray of bright cyan "
        "stars and sparkles"
    ),
}

DEFAULT_SEEDS = (11, 22, 33)


def compose(subject: str, style: str = STYLE) -> str:
    return f"{style}, {subject}"


def build_graph(prompt: str, negative: str, seed: int, size: int, prefix: str,
                model: str = "base", steps: int | None = None, cfg: float | None = None) -> dict:
    """Z-Image txt2img + BiRefNet alpha tail. Saves RGBA (node 14) and the opaque render (node 15)."""
    if model not in MODELS:
        raise SystemExit(f"unknown model {model!r}; valid: {', '.join(MODELS)}")
    preset = MODELS[model]
    steps = preset["steps"] if steps is None else steps
    cfg = preset["cfg"] if cfg is None else cfg
    negative_node = (
        {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
        if preset["zero_negative"]
        else {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 0]}}
    )
    return {
        "1": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 0]}},
        "3": negative_node,
        "4": {"class_type": "UNETLoader",
              "inputs": {"unet_name": preset["unet"], "weight_dtype": "default"}},
        "5": {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": ["4", 0], "shift": preset["shift"]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": size, "height": size, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": preset["sampler"], "scheduler": preset["scheduler"],
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["6", 0]}},
        # alpha tail — RemoveBackground's mask marks the BACKGROUND, so invert it before joining.
        "10": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": BG_MODEL}},
        "11": {"class_type": "RemoveBackground",
               "inputs": {"image": ["9", 0], "bg_removal_model": ["10", 0]}},
        "12": {"class_type": "InvertMask", "inputs": {"mask": ["11", 0]}},
        "13": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["9", 0], "alpha": ["12", 0]}},
        "14": {"class_type": "SaveImage",
               "inputs": {"images": ["13", 0], "filename_prefix": f"{prefix}_rgba"}},
        "15": {"class_type": "SaveImage",
               "inputs": {"images": ["9", 0], "filename_prefix": f"{prefix}_opaque"}},
    }


def recipe(prompt: str, negative: str, seed: int, size: int, model: str, graph: dict) -> dict:
    """Everything needed to replay this candidate exactly."""
    preset = MODELS[model]
    ks = graph["8"]["inputs"]
    return {
        "prompt": prompt,
        "negative": None if preset["zero_negative"] else negative,
        "seed": seed,
        "size": size,
        "model": model,
        "sampling": {"steps": ks["steps"], "cfg": ks["cfg"], "sampler": ks["sampler_name"],
                     "scheduler": ks["scheduler"], "shift": preset["shift"]},
        "models": {"unet": preset["unet"], "clip": CLIP, "vae": VAE, "bg": BG_MODEL},
        "graph": graph,
    }


def _download_node(server: str, hist: dict, node_id: str, dest: Path) -> Path:
    """Download one specific node's image to `dest`.

    Deliberately NOT comfy_client.download_outputs: that walks the history entry's nodes in server
    order, so the RGBA and the opaque render come back as `<stem>.png` / `<stem>_1.png` with no
    guarantee which is which. The node id is the identity, so address it directly."""
    entry = hist.get("outputs", {}).get(node_id, {})
    images = entry.get("images", [])
    if not images:
        raise SystemExit(f"node {node_id} produced no image; outputs={list(hist.get('outputs', {}))}")
    item = images[0]
    r = requests.get(f"{server.rstrip('/')}/view",
                     params={"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                             "type": item.get("type", "output")}, timeout=120)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def run_one(server: str, graph: dict, out_dir: Path, stem: str, backstop: float | None) -> Path:
    """Queue one graph, wait for terminal state, save `<stem>.png` (RGBA) + `<stem>_opaque.png`."""
    pid = comfy_client.queue(server, graph)
    hist = comfy_client.wait_for_history(server, pid, backstop=backstop, label=stem)
    rgba = _download_node(server, hist, "14", out_dir / f"{stem}.png")
    _download_node(server, hist, "15", out_dir / f"{stem}_opaque.png")
    return rgba


def generate(server: str, out_dir: Path, directions: dict[str, str], seeds, size: int,
             model: str, style: str, negative: str, backstop: float | None,
             steps: int | None = None, cfg: float | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for name, subject in directions.items():
        prompt = compose(subject, style)
        for seed in seeds:
            stem = f"{name}_s{seed}"
            graph = build_graph(prompt, negative, seed, size, f"asset_harness/emoji_{stem}",
                                model=model, steps=steps, cfg=cfg)
            print(f"[{stem}] queueing ...", flush=True)
            rgba = run_one(server, graph, out_dir, stem, backstop)
            (out_dir / f"{stem}.recipe.json").write_text(
                json.dumps(recipe(prompt, negative, seed, size, model, graph), indent=2),
                encoding="utf-8")
            print(f"[{stem}] -> {rgba.name}", flush=True)
            made.append(rgba)
    return made


def replay(server: str, recipe_path: Path, out_dir: Path, stem: str,
           backstop: float | None) -> Path:
    """Re-run a recorded recipe from its own record. The reproducibility check (plan Scenario 3b)."""
    rec = json.loads(recipe_path.read_text(encoding="utf-8"))
    return run_one(server, rec["graph"], out_dir, stem, backstop)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    ap.add_argument("--out", default="outputs/emoji", help="output directory")
    ap.add_argument("--model", default="base", choices=sorted(MODELS))
    ap.add_argument("--size", type=int, default=1024, help="square generation resolution")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    ap.add_argument("--directions", nargs="+", default=None,
                    help=f"subset of: {', '.join(DIRECTIONS)} (default: all)")
    ap.add_argument("--subject", default=None,
                    help="one-off subject, generated under the name given by --name")
    ap.add_argument("--name", default="custom", help="direction name for --subject")
    ap.add_argument("--style", default=STYLE)
    ap.add_argument("--negative", default=NEGATIVE)
    ap.add_argument("--steps", type=int, default=None, help="override the preset step count")
    ap.add_argument("--cfg", type=float, default=None, help="override the preset cfg")
    ap.add_argument("--backstop", type=float, default=None,
                    help="seconds before giving up on a job (default: no cap — a running job is "
                         "not a timeout; see comfy_client)")
    ap.add_argument("--replay", default=None, metavar="RECIPE.json",
                    help="re-run a recorded recipe instead of generating")
    args = ap.parse_args()

    out_dir = Path(args.out)
    if args.replay:
        stem = Path(args.replay).stem.replace(".recipe", "") + "_replay"
        print("  ", replay(args.server, Path(args.replay), out_dir, stem, args.backstop))
        return

    if args.subject:
        directions = {args.name: args.subject}
    elif args.directions:
        unknown = [d for d in args.directions if d not in DIRECTIONS]
        if unknown:
            raise SystemExit(f"unknown direction(s): {', '.join(unknown)}; "
                             f"valid: {', '.join(DIRECTIONS)}")
        directions = {d: DIRECTIONS[d] for d in args.directions}
    else:
        directions = DIRECTIONS

    made = generate(args.server, out_dir, directions, args.seeds, args.size,
                    args.model, args.style, args.negative, args.backstop,
                    steps=args.steps, cfg=args.cfg)
    print(f"\n{len(made)} file(s) in {out_dir}")


if __name__ == "__main__":
    main()
