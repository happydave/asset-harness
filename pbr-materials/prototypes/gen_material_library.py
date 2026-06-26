#!/usr/bin/env python3
"""Generate the Sounding structural-material library: Z-Image albedo (ai2) + local derivation.

Extends the proven hull_panel/rocky_ground pipeline (generate_materials.py) to the four
**structural** materials Sounding's voxel skin distinguishes — aluminium, steel, titanium,
composite (carbon-fibre) — plus a few bonus planetary-surface materials to grow the library
(sand, ice, basalt). Each: a flat shadowless albedo on ai2, then the Bevy-ready map set derived
locally (seamless albedo, normal, metallic-roughness, occlusion, height) + a tiled preview.

Run: python gen_material_library.py              (all materials)
     python gen_material_library.py steel_plate   (only the named materials — regen a subset)

Per-material optional keys: `normal_strength` (gentler => smoother relief; default 4.0) and `seed`
(override the shared SEED to break an unwanted composition).
"""
import json
import sys
from pathlib import Path

import gen_albedo
import derive_pbr

SERVER = "http://ai2:8188"
SEED = 424242
SIZE = 1024

# `albedo` carries only flat even base colour; the metal shine comes from the metallic/roughness
# maps + the engine's own lighting. Metals: dense micro-detail (so the model fills the frame with
# texture instead of rendering one big lit sweep), no "brushed/satin/polished" sweep words, and a
# `flatten` delight pass removes any residual baked gradient.
FLAT = ("seamless tileable PBR albedo texture swatch, flat lay overhead scan, even diffuse, "
        "no shadows no specular highlights no reflections, uniform tone edge to edge, "
        "fine surface texture filling the whole frame, ultra detailed")

# rough_base: higher => rougher overall (hull_panel used 150, rocky_ground 205).
# metal: flat metallic value packed into the metallic-roughness B channel.
# normal_strength: lower => smoother. flatten: delight a baked lighting gradient (flat metals).
MATERIALS = [
    # --- the four structural materials (WI 624) ---
    {"name": "aluminium_panel", "metal": 0.95, "rough_base": 130, "normal_strength": 3.0,
     "flatten": True,
     "subject": "light neutral silver-grey aluminium, surface densely covered edge to edge with "
                "fine horizontal hairline scratches, tiny scuffs and faint specks, uniform even "
                "tone, no central highlight, no gradient, no vignette, no panels, no rivets"},
    {"name": "steel_plate", "metal": 1.0, "rough_base": 100, "normal_strength": 3.5,
     "flatten": True,
     "subject": "medium blue-grey stainless steel, busy surface covered edge to edge with fine "
                "criss-cross scratches, scattered scuffs, small pits and faint mottled grain, "
                "uniform even tone, no central highlight, no gradient, no panels, no seams"},
    {"name": "titanium_panel", "metal": 0.9, "rough_base": 150, "normal_strength": 2.5,
     "seed": 991733, "flatten": True,
     "subject": "warm neutral grey titanium with a faint gold tint, dense uniform fine sandblasted "
                "micro-texture and tiny scratches across the whole frame, even matte tone, no "
                "central highlight, no radial sweep, no gradient, no panels, no squares, no grid"},
    {"name": "carbon_weave", "metal": 0.1, "rough_base": 120, "flatten": True,
     "subject": "dark charcoal carbon fibre composite, uniform fine 2x2 twill weave repeating edge "
                "to edge across the whole frame, subtle iridescent threads, even matte tone, no "
                "central highlight, no gradient, no vignette"},
    # --- bonus planetary-surface library (asset-harness growth, not wired by WI 624) ---
    {"name": "sand_dune", "metal": 0.0, "rough_base": 215,
     "subject": "fine wind-rippled desert sand, warm tan dunes, soft granular ripples, natural"},
    {"name": "ice_sheet", "metal": 0.0, "rough_base": 75,
     "subject": "cracked glacial ice sheet, pale blue-white, frosted surface with fine fracture "
                "lines and embedded air bubbles, glossy"},
    {"name": "basalt_rock", "metal": 0.0, "rough_base": 185,
     "subject": "dark volcanic basalt rock, near-black grey, vesicular pitted texture with sharp "
                "fractured facets, dry"},
]


def main() -> None:
    here = Path(__file__).parent
    out_root = here / "outputs" / "library"
    raw = out_root / "raw"
    only = set(sys.argv[1:])  # optional: regenerate just the named materials
    selected = [m for m in MATERIALS if not only or m["name"] in only]
    manifest = []
    for m in selected:
        name = m["name"]
        prompt = f"{FLAT}, {m['subject']}"
        seed = m.get("seed", SEED)
        strength = m.get("normal_strength", 4.0)
        flatten = m.get("flatten", False)
        print(f"\n=== {name} (seed {seed}, normal {strength}, flatten {flatten}) ===")
        albedo = gen_albedo.generate_albedo(SERVER, prompt, seed, SIZE, raw, name)
        print(f"  albedo {albedo.name}; deriving maps ...")
        paths = derive_pbr.derive(albedo, out_root / name, name,
                                  metal=m["metal"], rough_base=m["rough_base"],
                                  normal_strength=strength, flatten=flatten)
        manifest.append({"name": name, "metal": m["metal"], "rough_base": m["rough_base"],
                         "seed": seed, "normal_strength": strength, "flatten": flatten,
                         "prompt": prompt, "maps": {k: v.name for k, v in paths.items()}})
    # Merge into the existing manifest so a subset run does not drop the untouched materials.
    mf_path = out_root / "materials_manifest.json"
    existing = {}
    if mf_path.exists():
        for e in json.loads(mf_path.read_text()).get("materials", []):
            existing[e["name"]] = e
    for e in manifest:
        existing[e["name"]] = e
    mf_path.write_text(json.dumps(
        {"seed": SEED, "size": SIZE, "server": SERVER,
         "materials": [existing[k] for k in sorted(existing)]}, indent=2))
    print(f"\nmanifest -> {mf_path}")


if __name__ == "__main__":
    main()
