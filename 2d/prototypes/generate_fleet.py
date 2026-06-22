#!/usr/bin/env python3
"""Generate a small, style-coherent DWA fleet through the clean Z-Image harness.

Demonstrates the STYLE ANCHOR: one shared house-style preamble + a fixed seed across all
ships, with only the per-ship subject + control primitive changing. This is how we keep a
set visually consistent without LoRAs/IPAdapter.

Outputs each ship's RGBA/opaque/canny into <out>/, ready for build_atlas.py.
"""
import json
import uuid
from pathlib import Path

import make_primitives
from run_zimage_controlnet import (STYLE, build_graph, compose, download,
                                   queue, upload_image, wait)

SERVER = "http://ai2:8188"
FLEET_SEED = 729703840979498   # fixed across the fleet for coherence
STRENGTH = 0.85

FLEET = [
    {"name": "hauler",
     "subject": "a heavy cargo hauler with armored greebled hull, square side cargo pods, "
                "and three engine nozzles with a faint glow"},
    {"name": "miner",
     "subject": "a compact mining vessel with a forward rotary drilling rig, "
                "two round ore storage tanks, and a small twin-nozzle engine"},
]


def main() -> None:
    here = Path(__file__).parent
    in_dir = here / "inputs"
    out_dir = here / "outputs" / "fleet"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # (re)generate all primitives
    for name in (s["name"] for s in FLEET):
        make_primitives.SHIPS[name](in_dir / f"{name}_primitive.png")

    manifest = []
    for ship in FLEET:
        name = ship["name"]
        prompt = compose(ship["subject"], STYLE)
        print(f"\n=== {name} ===")
        control = upload_image(SERVER, in_dir / f"{name}_primitive.png")
        graph = build_graph(control, prompt, FLEET_SEED, STRENGTH, prefix=f"asset_harness/{name}")
        pid = queue(SERVER, graph, uuid.uuid4().hex)
        print(f"  prompt_id={pid}; waiting ...")
        hist = wait(SERVER, pid)
        saved = download(SERVER, hist, out_dir)
        rgba = [p for p in saved if "_rgba_" in p.name]
        print(f"  saved {len(saved)} files; rgba={[p.name for p in rgba]}")
        manifest.append({"name": name, "prompt": prompt, "seed": FLEET_SEED,
                         "rgba": rgba[0].name if rgba else None})

    (out_dir / "fleet_manifest.json").write_text(json.dumps(
        {"style": STYLE, "strength": STRENGTH, "ships": manifest}, indent=2))
    print(f"\nfleet manifest -> {out_dir/'fleet_manifest.json'}")


if __name__ == "__main__":
    main()
