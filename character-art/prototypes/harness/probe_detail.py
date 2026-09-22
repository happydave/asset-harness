#!/usr/bin/env python3
"""Run one detail pass on one image and say what the detector did.

    python3 probe_detail.py --server http://127.0.0.1:7124 --input-dir ~/wi1732/input \\
                            --image dragonborn_upscale.png --detector face \\
                            --prompt "..." --seed 404 --out ~/wi1732/probe

Uses the harness's own graph and verdict (`chain.detail`, `chain.detail_verdict`) and the driver's
job runner, so it answers exactly the question the batch asks: detected? pixels changed? which of
the four cells? Only the mask can tell a detector that found nothing from one that fired and did
nothing; the pixels are the same either way.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chain
import run_batch as RB

DETECTORS = {"face": chain.FACE_DETECTOR, "hand": chain.HAND_DETECTOR}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:7124")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--image", required=True, help="filename inside --input-dir")
    ap.add_argument("--detector", choices=sorted(DETECTORS), required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True, help="where the job's two images are kept")
    args = ap.parse_args()

    src = Path(args.input_dir) / args.image
    before = src.read_bytes()
    stem = Path(args.image).stem
    prefix = f"wi1732/{stem}_{args.detector}"
    graph = chain.detail(args.image, DETECTORS[args.detector], args.prompt, args.seed, prefix)
    outputs = RB._run_job(args.server, graph, f"probe:{stem}:{args.detector}", Path(args.out))
    image, mask = RB._split_detail_outputs(outputs, f"probe:{stem}", prefix)
    detected = chain.mask_detected(mask.read_bytes())
    changed = not chain.is_inert(before, image.read_bytes())
    v = chain.detail_verdict(detected, changed)
    print(f"{args.image} / {args.detector}: detected={detected} pixels_changed={changed} "
          f"-> {v.outcome}: {v.reason}")
    print(f"  image {image}\n  mask  {mask}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
