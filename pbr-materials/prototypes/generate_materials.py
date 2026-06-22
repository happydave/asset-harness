#!/usr/bin/env python3
"""Generate Sounding-ready PBR material sets: Z-Image albedo (ai2) + local derivation.

For each material: generate a flat shadowless albedo on ai2, then derive the Bevy-ready map set
locally (seamless albedo, normal, metallic-roughness, occlusion, height) + a tiled preview.
"""
import json
from pathlib import Path

import gen_albedo
import derive_pbr

SERVER = "http://ai2:8188"
SEED = 424242
SIZE = 1024

FLAT = ("seamless tileable PBR base color texture, flat even diffuse lighting, no shadows, "
        "no specular highlights, top-down orthographic, photoscan albedo, ultra detailed")

MATERIALS = [
    {"name": "hull_panel", "metal": 0.85, "rough_base": 150,
     "subject": "weathered spacecraft hull metal panel, scuffed gunmetal-grey paint with "
                "rust-orange streaks, rivets and recessed panel seams"},
    {"name": "rocky_ground", "metal": 0.0, "rough_base": 205,
     "subject": "rocky planetary ground, cracked dry greyish regolith with scattered pebbles "
                "and fine dust, natural"},
]


def main() -> None:
    here = Path(__file__).parent
    out_root = here / "outputs"
    manifest = []
    for m in MATERIALS:
        name = m["name"]
        prompt = f"{FLAT}, {m['subject']}"
        print(f"\n=== {name} ===")
        albedo = gen_albedo.generate_albedo(SERVER, prompt, SEED, SIZE, out_root / "raw", name)
        print(f"  albedo {albedo.name}; deriving maps ...")
        mat_dir = out_root / name
        paths = derive_pbr.derive(albedo, mat_dir, name, metal=m["metal"], rough_base=m["rough_base"])
        manifest.append({"name": name, "metal": m["metal"], "prompt": prompt,
                         "maps": {k: v.name for k, v in paths.items()}})
    (out_root / "materials_manifest.json").write_text(
        json.dumps({"seed": SEED, "size": SIZE, "materials": manifest}, indent=2))
    print(f"\nmanifest -> {out_root/'materials_manifest.json'}")


if __name__ == "__main__":
    main()
