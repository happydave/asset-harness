#!/usr/bin/env python3
"""Generate the WI 1599 cast across every installed booru-tag checkpoint, family-correct.

WI 1630. The comparison is only about the checkpoint if everything else is held: same subjects,
same seeds, same sampler, steps, CFG and resolution as WI 1617 used, so a result here is
comparable to what that sidequest already recorded.

The one thing that is deliberately *not* held is the quality prefix. Pony and Illustrious take
different ones, and running Illustrious's on a Pony checkpoint would handicap it for a reason that
has nothing to do with race features -- which is the axis under test. Pony's score chain is used
verbatim and never negated, per its author's own account (WI 1591 round 2).

    python3 sweep.py --out out --server http://127.0.0.1:8188 --stage 1
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import comfy_client as cc

# Read from /opt/comfyui/models/checkpoints on ai2. Family is read from the filename, which is a
# community naming convention rather than a guarantee -- FC3 tests the consequence that matters.
CHECKPOINTS = {
    "wai":        ("waiIllustriousSDXL_v170.safetensors", "illustrious"),
    "ilustmix":   ("ilustmix_v9.safetensors", "illustrious"),
    "nova3dcg":   ("nova3DCGXL_illlustriousV50.safetensors", "illustrious"),
    "prefectpony": ("prefectPonyXL_v6.safetensors", "pony"),
    "ponyrealism": ("ponyRealism_V23.safetensors", "pony"),
    "cyberpony":  ("cyberrealisticPony_v180Coreshift.safetensors", "pony"),
}

PREFIX = {
    "illustrious": "masterpiece, best quality, very aesthetic, absurdres",
    # Verbatim and three-term: score_9 alone is much weaker, and the model learned the string as
    # one concept rather than as a scale.
    "pony": "score_9, score_8_up, score_7_up",
}

# The e621-derived sub-corpus, which is where anthro, scaled and horned subjects actually live.
FURRY = "source_furry"

NEG = ("bad quality, worst quality, worst detail, sketch, censored, blurry, lowres, "
       "jpeg artifacts, extra digits, fewer digits, bad hands, text, watermark, signature")

NON_HUMAN = ("tiefling", "dragonborn", "halforc")


def load_cast(roster: Path) -> list[dict]:
    with roster.open() as f:
        rows = [r for r in csv.DictReader(f) if r["identity_features"].strip()]
    out = []
    for r in rows:
        # Strip the roster's own Illustrious prefix; the family prefix is applied per arm.
        tags = r["tags"]
        for p in ("masterpiece, best quality, very aesthetic, absurdres, ", ):
            tags = tags.replace(p, "")
        out.append({"id": r["id"], "tags": tags, "seed": int(r["seed"]),
                    "features": r["identity_features"]})
    return out


def graph(ckpt: str, prompt: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPSetLastLayer",
              "inputs": {"clip": ["1", 1], "stop_at_clip_layer": -2}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEG}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 768, "height": 1344, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "seed": seed, "steps": 30, "cfg": 5.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }


def arms(cast, stage: int, only_ckpt=None, seeds=None):
    """One dict per image to generate."""
    for key, (ckpt, family) in CHECKPOINTS.items():
        if only_ckpt and key != only_ckpt:
            continue
        for ch in cast:
            for seed in (seeds or [ch["seed"]]):
                variants = [False]
                if family == "pony" and ch["id"] in NON_HUMAN:
                    variants = [False, True]
                for furry in variants:
                    bits = [PREFIX[family]]
                    if furry:
                        bits.append(FURRY)
                    bits.append(ch["tags"])
                    name = f"{key}_{ch['id']}_s{seed}" + ("_furry" if furry else "")
                    yield {"name": name, "ckpt": ckpt, "ckpt_key": key, "family": family,
                           "subject": ch["id"], "seed": seed, "source_furry": furry,
                           "prompt": ", ".join(bits), "features": ch["features"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--roster", default="../../roster/cast.csv")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--stage", type=int, default=1)
    ap.add_argument("--only-ckpt")
    ap.add_argument("--seeds", help="comma-separated, overrides the cast seeds")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cast = load_cast(Path(a.roster))
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else None
    jobs = list(arms(cast, a.stage, a.only_ckpt, seeds))
    print(f"{len(jobs)} images")
    if a.dry_run:
        for j in jobs:
            print(f"  {j['name']:34s} {j['prompt'][:80]}")
        return 0

    manifest = []
    for i, j in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {j['name']}", flush=True)
        got = cc.run_job(a.server, graph(j["ckpt"], j["prompt"], j["seed"], f"wi1630/{j['name']}"),
                         out / j["name"], label=j["name"])
        if not got:
            raise SystemExit(f"{j['name']}: no image produced")
        manifest.append({**j, "path": str(got[0])})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"\n{len(manifest)} images -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
