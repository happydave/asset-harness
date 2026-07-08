#!/usr/bin/env python3
"""Generate the Sounding material library: Z-Image albedo (ai2) + local derivation.

Extends the proven hull_panel/rocky_ground pipeline (generate_materials.py) to the four
**structural** materials Sounding's voxel skin distinguishes — aluminium, steel, titanium,
composite (carbon-fibre) — plus bonus planetary-surface materials (sand_dune, ice_sheet,
basalt_rock) and the ten **terrain** sets named by Sounding's biome table (WI 871: grass,
steppe, sand, mud, forest_floor, rock, snow, regolith_fine, regolith_coarse, basalt). Each: a
flat shadowless albedo on ai2, then the Bevy-ready map set derived locally (seamless albedo,
normal, metallic-roughness, occlusion, height) + a tiled preview.

Run: python gen_material_library.py              (all materials)
     python gen_material_library.py steel_plate   (only the named materials — regen a subset)

Per-material optional keys: `normal_strength` (gentler => smoother relief; default 4.0), `seed`
(override the shared SEED to break an unwanted composition), `flatten` (delight a baked lighting
gradient), and `tone` (anchor the albedo's mean colour to a target sRGB — the terrain sets use
their consuming biomes' tints).
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
    # --- terrain library for the Sounding biome layer (WI 871) ---
    # Names are fixed by Sounding's biome table (`texture_set` values); albedo hue anchors to the
    # consuming biomes' tints so the far-LOD tint -> near-texture transition stays in family.
    {"name": "grass", "tone": (0.35, 0.48, 0.22), "metal": 0.0, "rough_base": 200, "seed": 777001, "flatten": True,
     "subject": "short dry meadow grass seen from directly above, muted olive green turf with "
                "faint brown dry blades mixed in, fine blade texture, uniform density edge to "
                "edge, even tone, no stripes, no mowing lines, no gradient, natural and dull"},
    {"name": "steppe", "tone": (0.50, 0.47, 0.30), "metal": 0.0, "rough_base": 210,
     "subject": "dry steppe grassland from directly above, sparse straw-yellow dry grass tufts "
                "and pale lichen on dusty grey-brown cracked soil, arid ground"},
    {"name": "sand", "tone": (0.74, 0.65, 0.44), "metal": 0.0, "rough_base": 215, "normal_strength": 3.0,
     "seed": 777002, "flatten": True,
     "subject": "fine desert sand from directly above, pale desaturated beige tan, small "
                "closely spaced fine wind ripples repeating edge to edge, uniform even muted "
                "tone, no large dunes, no gradient, dry granular surface, dull natural colour"},
    {"name": "mud", "tone": (0.20, 0.28, 0.16), "metal": 0.0, "rough_base": 140, "flatten": True,
     "subject": "dark greenish-brown damp organic swamp mud from directly above, matte, "
                "fine cracks and small ruts evenly across the whole frame, scattered tiny "
                "decaying leaf fragments, no shine, no highlights, no gradient"},
    # forest_floor tone is a deliberate compromise, not the raw tint mean (0.15, 0.29, 0.17):
    # matching that green-dominant anchor from the model's brown-leaning source halves R and
    # doubles B, turning bright needle strands cyan. This keeps the set green-leaning while the
    # needles stay natural; the residual far-tint hue drift is small and B5 can tint-modulate.
    {"name": "forest_floor", "tone": (0.20, 0.28, 0.10), "metal": 0.0, "rough_base": 195, "seed": 424777, "flatten": True,
     "subject": "mossy forest floor from directly above, deep green moss and dark brown soil "
                "mixed evenly, scattered pine needles and small twigs, ground fills the whole "
                "frame full bleed, no border, no frame, no vignette, no rows, no clusters"},
    {"name": "rock", "tone": (0.40, 0.39, 0.38), "metal": 0.0, "rough_base": 190,
     "subject": "fractured rock scree from directly above, angular broken mid-grey stone "
                "fragments over exposed cracked bedrock, neutral grey, dry mountain surface"},
    {"name": "snow", "tone": (0.85, 0.90, 0.95), "metal": 0.0, "rough_base": 140, "normal_strength": 2.5,
     "seed": 777004, "flatten": True,
     "subject": "smooth clean packed snow from directly above, bright blue-white, uniform "
                "fine grain and faint small ripples edge to edge, even tone, no footprints, "
                "no tracks, no debris, no rocks, no gradient"},
    {"name": "regolith_fine", "tone": (0.51, 0.50, 0.49), "metal": 0.0, "rough_base": 225, "normal_strength": 3.0,
     "seed": 777005, "flatten": True,
     "subject": "fine lunar regolith from directly above, neutral medium grey powder dust, "
                "uniform fine grain with tiny pits and small compacted clods edge to edge, "
                "even tone, no rocks, no stones, no gradient, dry airless soil"},
    {"name": "regolith_coarse", "tone": (0.35, 0.35, 0.36), "metal": 0.0, "rough_base": 210, "seed": 777006,
     "flatten": True,
     "subject": "coarse lunar regolith from directly above, small angular grey rock fragments "
                "half-buried in grey dust, evenly scattered edge to edge, uniform density, "
                "no large boulders, no empty areas, no gradient"},
    {"name": "basalt", "tone": (0.22, 0.22, 0.23), "metal": 0.0, "rough_base": 190,
     "subject": "dark volcanic basalt lava plain from directly above, near-black grey vesicular "
                "basalt with fine pits and broken cooled plates, dry"},
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
        tone = m.get("tone")
        print(f"\n=== {name} (seed {seed}, normal {strength}, flatten {flatten}, tone {tone}) ===")
        albedo = gen_albedo.generate_albedo(SERVER, prompt, seed, SIZE, raw, name)
        print(f"  albedo {albedo.name}; deriving maps ...")
        paths = derive_pbr.derive(albedo, out_root / name, name,
                                  metal=m["metal"], rough_base=m["rough_base"],
                                  normal_strength=strength, flatten=flatten, tone=tone)
        manifest.append({"name": name, "metal": m["metal"], "rough_base": m["rough_base"],
                         "seed": seed, "normal_strength": strength, "flatten": flatten,
                         "tone": tone, "prompt": prompt,
                         "maps": {k: v.name for k, v in paths.items()}})
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
