#!/usr/bin/env python3
"""Generate the AI PBR material sets the rover parts are skinned with — the "AI surface" half of the
mechanical-kit premise. Reuses the pbr-materials track: Z-Image flat albedo on `ai2` + local
derivation to a Bevy-ready map set (albedo / normal / metallic-roughness / occlusion).

Outputs ./materials/<name>/<name>_{albedo,normal,metallic_roughness,occlusion,height}.png — pushed to
`ai2` and bound onto the parts by blender_texture_parts.py. Fully clean (Z-Image = Apache).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pbr-materials" / "prototypes"))
import gen_albedo   # noqa: E402
import derive_pbr   # noqa: E402

SERVER = "http://ai2:8188"
SIZE = 512
HERE = Path(__file__).parent
OUT = HERE / "materials"
STYLE = ("flat even diffuse lighting, no shadows, no specular highlights, top-down orthographic, "
         "seamless tileable texture, photoscan albedo, ultra detailed")

# Material sets keyed to the part catalog. metal / rough_base feed the local PBR derivation.
MATERIALS = [
    {"name": "metal_panel", "seed": 720, "metal": 0.9, "rough_base": 110,
     "prompt": "brushed aluminium spacecraft hull panel, fine horizontal brushed metal grain, "
               "faint scratches and micro-wear, light neutral grey, industrial"},
    {"name": "rubber", "seed": 721, "metal": 0.0, "rough_base": 205,
     "prompt": "black rubber tire tread, matte vulcanised rubber, fine grain with a subtle blocky "
               "tread pattern, very dark charcoal"},
    {"name": "solar_cells", "seed": 722, "metal": 0.25, "rough_base": 70,
     "prompt": "photovoltaic solar panel surface, regular grid of dark blue monocrystalline cells "
               "with thin silver busbar lines, glossy, deep blue"},
    {"name": "seat_fabric", "seed": 723, "metal": 0.0, "rough_base": 190,
     "prompt": "dark grey technical seat upholstery, woven padded fabric with subtle quilting, "
               "matte, fine textile weave"},
    {"name": "leather_light", "seed": 724, "metal": 0.0, "rough_base": 150,
     "prompt": "light tan leather upholstery, soft full-grain natural leather with fine pores and "
               "subtle stitched seams, warm cream beige"},
    {"name": "solar_cells_2x1", "seed": 725, "metal": 0.25, "rough_base": 70,
     "prompt": "photovoltaic solar panel, regular grid of rectangular two-to-one landscape "
               "monocrystalline cells with thin silver busbar lines, glossy, deep blue"},
    {"name": "white_hull", "seed": 726, "metal": 0.1, "rough_base": 80,
     "prompt": "white painted aerospace hull panel, glossy clean white with faint panel seams and "
               "subtle scuffs, smooth"},
    {"name": "heat_metal", "seed": 727, "metal": 0.9, "rough_base": 130,
     "prompt": "heat-discoloured inconel rocket nozzle metal, blue and gold heat tint with soot "
               "streaks and fine machining lines, metallic"},
    {"name": "screen_ui", "seed": 728, "metal": 0.1, "rough_base": 30,
     "prompt": "dark glass tablet touchscreen displaying a faint glowing user interface with app "
               "icons, gauges and widgets, deep black glass, cyan and white accents"},
]


def main() -> None:
    import sys as _sys
    only = _sys.argv[_sys.argv.index("--only") + 1].split(",") if "--only" in _sys.argv else None
    for m in MATERIALS:
        if only and m["name"] not in only:
            continue
        name = m["name"]
        mat_dir = OUT / name
        prompt = f"{m['prompt']}, {STYLE}"
        print(f"[{name}] albedo on ai2 ...")
        albedo = gen_albedo.generate_albedo(SERVER, prompt, m["seed"], SIZE, OUT / "raw", name)
        paths = derive_pbr.derive(albedo, mat_dir, name, metal=m["metal"], rough_base=m["rough_base"])
        print(f"[{name}] -> {mat_dir} ({len(paths)} maps)")


if __name__ == "__main__":
    main()
