#!/usr/bin/env python3
"""Generate spider-miner LEG-SEGMENT sprite CANDIDATES for DWA WI 818.

Mirrors generate_spider_miner.py (WI 813): a single subject + one control primitive + the shared
STYLE anchor, sweeping the SEED across N candidates so Dave can pick the final. The subject is a
single reusable leg segment (DWA WI 817 stretches it along each rig segment and rotates it into
pose), so it is DIRECTIONAL: pivot-joint end -> drill-tip end, tool (drill/chainsaw) edge on one
side. Same fleet seed family + STYLE as the WI 813 body, so the leg reads as the same machine.

Outputs -> outputs/leg_segment/.  Once picked, atlas the chosen RGBA with build_atlas.py.
"""
import argparse
import json
import uuid
from pathlib import Path

import make_primitives
from generate_spider_miner import contact_sheet
from run_zimage_controlnet import (STYLE, build_graph, download, queue,
                                   upload_image, wait)

SERVER = "http://ai2:8188"
BASE_SEED = 729703840979498          # same family as the shipped fleet + WI 813 body (coherence)
STRENGTH = 0.85

SUBJECT = (
    "a single articulated mechanical leg segment of an asteroid-mining spider drone, shown flat "
    "in orthographic side view, an elongated tapered armored limb with a round pivot joint at the "
    "left end and a pointed rotary drill tip at the right end, the lower inner edge lined with "
    "rock-cutting drill teeth and chainsaw blades, heavy weathered industrial machinery, isolated"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--count", type=int, default=6, help="number of seed candidates")
    ap.add_argument("--strength", type=float, default=STRENGTH)
    ap.add_argument("--out", default="outputs/leg_segment")
    args = ap.parse_args()

    server = args.server.rstrip("/")
    here = Path(__file__).parent
    in_dir = here / "inputs"
    out_dir = (here / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    make_primitives.leg_segment(in_dir / "leg_segment_primitive.png")
    control = upload_image(server, in_dir / "leg_segment_primitive.png")
    prompt = f"{STYLE}, {SUBJECT}"
    seeds = [BASE_SEED + i * 101 for i in range(args.count)]

    manifest = []
    rgba_paths = []
    for i, seed in enumerate(seeds):
        name = f"cand{i:02d}"
        print(f"\n=== {name} (seed={seed}) ===")
        graph = build_graph(control, prompt, seed, args.strength,
                            prefix=f"asset_harness/leg_segment_{name}")
        pid = queue(server, graph, uuid.uuid4().hex)
        print(f"  prompt_id={pid}; waiting ...")
        hist = wait(server, pid)
        saved = download(server, hist, out_dir)
        rgba = [p for p in saved if "_rgba_" in p.name]
        if rgba:
            rgba_paths.append(rgba[0])
        print(f"  saved {len(saved)} files; rgba={[p.name for p in rgba]}")
        manifest.append({"name": name, "seed": seed,
                         "rgba": rgba[0].name if rgba else None})

    (out_dir / "candidates_manifest.json").write_text(json.dumps(
        {"subject": SUBJECT, "style": STYLE, "strength": args.strength,
         "base_seed": BASE_SEED, "candidates": manifest}, indent=2))

    if rgba_paths:
        contact_sheet(rgba_paths, out_dir / "contact_sheet.png")
        print(f"\ncontact sheet -> {out_dir/'contact_sheet.png'}")
    print(f"manifest -> {out_dir/'candidates_manifest.json'}")


if __name__ == "__main__":
    main()
