#!/usr/bin/env python3
"""Generate a style-coherent, grid/slot station-module kit via the clean Z-Image harness.

Same style anchor + fixed seed as the ship fleet (so station and ships share a look), with a
module-specific framing. Higher ControlNet strength so the square footprint and edge ports stay
put. Outputs each module's RGBA/opaque/canny into outputs/modules/, ready for
`build_atlas.py --cell N` (grid mode, no trim → ports stay aligned).
"""
import json
import uuid
from pathlib import Path

import make_modules
from run_zimage_controlnet import (build_graph, compose, download, queue,
                                   upload_image, wait)

SERVER = "http://ai2:8188"
SEED = 729703840979498        # shared with the fleet for cross-coherence
STRENGTH = 0.9                # strong structure adherence to keep ports in place

MODULE_STYLE = (
    "top-down orthographic game sprite of a modular space station component, square form factor, "
    "mechanical docking ports centered on the connecting edges, industrial used-future, "
    "weathered painted steel hull, gunmetal grey with rust-orange hazard accents, "
    "soft even studio lighting, clean readable, isolated on a plain solid white background, "
    "crisp detailed concept art"
)

MODULES = [
    {"name": "hub", "subject": "a central command hub with a domed core and four connection ports"},
    {"name": "tank", "subject": "a cylindrical resource storage tank with banded plating, ports top and bottom"},
    {"name": "habitat", "subject": "a crew habitat module with rows of lit windows, ports top and bottom"},
    {"name": "solar", "subject": "a power module with two large photovoltaic panel wings and a central spine"},
    {"name": "dock", "subject": "a docking port module with a circular berthing ring and clamps"},
]


def main() -> None:
    here = Path(__file__).parent
    in_dir = here / "inputs"
    out_dir = here / "outputs" / "modules"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    for m in MODULES:
        make_modules.MODULES[m["name"]](in_dir / f"module_{m['name']}_primitive.png")

    manifest = []
    for m in MODULES:
        name = m["name"]
        prompt = compose(m["subject"], MODULE_STYLE)
        print(f"\n=== {name} ===")
        control = upload_image(SERVER, in_dir / f"module_{name}_primitive.png")
        graph = build_graph(control, prompt, SEED, STRENGTH, prefix=f"asset_harness/module_{name}")
        pid = queue(SERVER, graph, uuid.uuid4().hex)
        print(f"  prompt_id={pid}; waiting ...")
        hist = wait(SERVER, pid)
        saved = download(SERVER, hist, out_dir)
        rgba = [p for p in saved if "_rgba_" in p.name]
        print(f"  rgba={[p.name for p in rgba]}")
        manifest.append({"name": name, "prompt": prompt, "seed": SEED,
                         "rgba": rgba[0].name if rgba else None})

    (out_dir / "fleet_manifest.json").write_text(json.dumps(
        {"style": MODULE_STYLE, "strength": STRENGTH, "ships": manifest}, indent=2))
    print(f"\nmodule manifest -> {out_dir/'fleet_manifest.json'}")


if __name__ == "__main__":
    main()
