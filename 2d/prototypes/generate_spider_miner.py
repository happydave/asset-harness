#!/usr/bin/env python3
"""Generate spider-miner body/head sprite CANDIDATES for DWA WI 813.

Single subject + single control primitive + the shared STYLE anchor, sweeping the SEED across N
candidates so Dave can pick the final. Seed is the harness's coherence-preserving lever (see
generate_fleet.py): everything else is held fixed, so the candidates are the "same design, rolled
a few times." Writes each candidate's RGBA/opaque/canny, a manifest, and a single contact-sheet
image for side-by-side comparison.

The subject is deliberately NON-DIRECTIONAL (radially symmetric, no front/rear) because the DWA
entity Image is drawn un-rotated and facing is conveyed by the procedural legs (WI 805-807).

Outputs -> outputs/spider_miner/.  Once picked, atlas the chosen RGBA with build_atlas.py.
"""
import argparse
import json
import uuid
from pathlib import Path

from PIL import Image

import make_primitives
from run_zimage_controlnet import (STYLE, build_graph, download, queue,
                                   upload_image, wait)

SERVER = "http://ai2:8188"
BASE_SEED = 729703840979498          # same family as the shipped fleet (coherence)
STRENGTH = 0.85

SUBJECT = (
    "a radially symmetric asteroid-mining drone seen from directly above, a hexagonal armored "
    "hub with a central rotary rock-crusher maw ringed by teeth, eight short leg-mount sockets "
    "spaced evenly around the rim, compact and squat, no front or rear, no cockpit"
)


def contact_sheet(rgbas, out_path: Path, cell: int = 256, cols: int = 3) -> None:
    """Trim each RGBA to alpha bbox, fit into a `cell` square, grid them on a mid-grey sheet."""
    tiles = []
    for p in rgbas:
        im = Image.open(p).convert("RGBA")
        bbox = im.getchannel("A").getbbox()
        if bbox:
            im = im.crop(bbox)
        w, h = im.size
        s = (cell - 16) / max(w, h)
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        tiles.append((p.stem, im))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (90, 90, 96, 255))
    for i, (_, im) in enumerate(tiles):
        cx = (i % cols) * cell + (cell - im.size[0]) // 2
        cy = (i // cols) * cell + (cell - im.size[1]) // 2
        sheet.alpha_composite(im, (cx, cy))
    sheet.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--count", type=int, default=6, help="number of seed candidates")
    ap.add_argument("--strength", type=float, default=STRENGTH)
    ap.add_argument("--out", default="outputs/spider_miner")
    args = ap.parse_args()

    server = args.server.rstrip("/")
    here = Path(__file__).parent
    in_dir = here / "inputs"
    out_dir = (here / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    make_primitives.spider_miner(in_dir / "spider_miner_primitive.png")
    control = upload_image(server, in_dir / "spider_miner_primitive.png")
    prompt = f"{STYLE}, {SUBJECT}"
    seeds = [BASE_SEED + i * 101 for i in range(args.count)]

    manifest = []
    rgba_paths = []
    for i, seed in enumerate(seeds):
        name = f"cand{i:02d}"
        print(f"\n=== {name} (seed={seed}) ===")
        graph = build_graph(control, prompt, seed, args.strength,
                            prefix=f"asset_harness/spider_miner_{name}")
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
