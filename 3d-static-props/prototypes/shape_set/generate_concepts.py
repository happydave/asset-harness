#!/usr/bin/env python3
"""Concept stills for the shape test set (WI 2112): one opaque prop image per shape, the
image-to-3D lane's input.

Z-Image txt2img, opaque RGB (the lane's own BiRefNet node cuts the prop out). Turbo, because the
target server (`gtr`'s comfyui.service) has Turbo and not Base installed; Turbo ignores the negative
and varies little with the seed, so two seeds a shape are made and one is picked by looking.

Writes <out>/<shape>_s<seed>.png and a recipe JSON beside each (prompt, seed, settings, models and
the submitted graph). Stdlib + requests; uses the 2d lane's ComfyUI client.

  generate_concepts.py --server http://gtr:8188 --out OUTDIR [--seeds 11 12] [--manifest M.json [--only NAME ...]]

With --manifest, the shapes, frame and provisional marks come from the manifest (WI 2120's
zone_pool_manifest.json) instead of the built-in five, and each recipe carries the marks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "2d" / "prototypes"))
import comfy_client  # noqa: E402

UNET, CLIP, CLIP_TYPE, VAE = "z_image_turbo_bf16.safetensors", "qwen_3_4b.safetensors", "lumina2", "ae.safetensors"
STEPS, CFG, SAMPLER, SCHEDULER, SHIFT = 8, 1.0, "res_multistep", "simple", 3.0
SIZE = 1024

# The lane wants one whole object, centred, on a plain background it can cut away, seen from a
# three-quarter view so its depth reads. The style clause is Look 1's: painted, game-prop.
FRAME = ("Three-quarter view from slightly above, the whole object in frame and centred, on a plain light grey "
         "background, soft even studio light, a stylised hand-painted fantasy game prop, clean readable shapes.")
SHAPES = {
    "barrel": "A single upright wooden barrel bound with three dark iron hoops, its staves bulging at the middle.",
    "stump": "A single old tree stump with a flat sawn top showing growth rings, rough bark, and thick roots spreading into the ground at its base.",
    "chair": "A single simple wooden chair with four square legs, a plank seat and a back of three vertical slats.",
    "bench": "A single long wooden bench: a thick plank seat resting on two sturdy trestle legs joined by a stretcher bar.",
    "lantern": "A single iron lantern standing on its base: a square frame with four glass panes, a candle inside, a peaked top and a ring handle.",
}


def graph(prompt: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": CLIP_TYPE}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": SHIFT}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": SIZE, "height": SIZE, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                  "latent_image": ["7", 0], "seed": seed, "steps": STEPS, "cfg": CFG,
                                                  "sampler_name": SAMPLER, "scheduler": SCHEDULER, "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12])
    ap.add_argument("--shapes", nargs="+", default=list(SHAPES))
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--only", nargs="+")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    subjects, frame, marks, wi = SHAPES, FRAME, {}, 2112
    if a.manifest:
        m = json.loads(a.manifest.read_text())
        subjects = {i["name"]: i["subject"] for i in m["items"]}
        frame, marks, wi = m["frame"], {"provisional": m["provisional"]}, m["work_item"]
        a.shapes = a.only or list(subjects)
    for shape in a.shapes:
        prompt = f"{subjects[shape]} {frame}"
        for seed in a.seeds:
            stem = a.out / f"{shape}_s{seed}"
            g = graph(prompt, seed, f"wi{wi}/{shape}_s{seed}")
            files = comfy_client.run_job(a.server, g, stem)
            recipe = {"work_item": wi, **marks, "shape": shape, "prompt": prompt, "seed": seed,
                      "model": {"unet": UNET, "clip": CLIP, "clip_type": CLIP_TYPE, "vae": VAE},
                      "settings": {"steps": STEPS, "cfg": CFG, "sampler": SAMPLER, "scheduler": SCHEDULER,
                                   "shift": SHIFT, "size": SIZE, "negative": "zeroed (Turbo)"},
                      "server": a.server, "outputs": [str(f) for f in files], "graph": g}
            Path(f"{stem}.recipe.json").write_text(json.dumps(recipe, indent=1))
            print(shape, seed, files, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
