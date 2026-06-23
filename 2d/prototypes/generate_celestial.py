#!/usr/bin/env python3
"""Generate DWA celestial bodies (planet + per-resource asteroids) via the clean Z-Image harness.

Same STYLE-ANCHOR technique as the fleet, but a celestial-neutral anchor (these are not
vessels). One shared style preamble + a seed family keep the set coherent; the per-subject
control primitive + prompt change the silhouette and material.

Emits two build_atlas-compatible manifests under outputs/celestial/:
  planet_manifest.json   -> later atlas `dwa_planet`   (one large frame)
  asteroid_manifest.json -> later atlas `dwa_asteroids` (iron/ice/silicates/rare-metals/unknown)
"""
import json
import uuid
from pathlib import Path

import make_celestial
from run_zimage_controlnet import (build_graph, compose, download, queue,
                                   upload_image, wait)

SERVER = "http://ai2:8188"
BASE_SEED = 729703840979498   # shared seed family (ties celestial set to the fleet style)

# Celestial-neutral house style: keep the clean-cutout framing/lighting/background that the
# matting + readable-sprite pipeline depends on; drop the vessel/steel-hull specifics.
CELESTIAL_STYLE = (
    "top-down orthographic game sprite, science-fiction celestial body, "
    "soft even lighting, clean readable silhouette, centered, "
    "isolated on a plain solid white background, crisp detailed concept art"
)

PLANET = {
    "name": "planet",
    "primitive": "planet",
    "strength": 0.85,
    "subject": (
        "a gas giant planet viewed from directly above its pole, concentric swirling cloud "
        "bands in deep blue-grey and slate, one large off-center cyclonic storm spot, "
        "subtle glowing atmospheric rim"
    ),
}

# Per-resource asteroids + an 'unknown' (used for scan-gated large asteroids, WI 586).
ASTEROIDS = [
    {"name": "iron", "primitive": "rock_a", "strength": 0.8,
     "subject": "a rugged metallic asteroid, pitted grey stone shot through with "
                "rust-orange iron ore veins and dull metallic flecks"},
    {"name": "ice", "primitive": "rock_b", "strength": 0.8,
     "subject": "a craggy icy asteroid, pale blue-white frozen surface with translucent "
                "ice facets, frost and subtle internal glow"},
    {"name": "silicates", "primitive": "rock_c", "strength": 0.8,
     "subject": "a rocky silicate asteroid, tan and grey stone with sharp angular facets "
                "and fine clinging dust"},
    {"name": "rare-metals", "primitive": "rock_a", "strength": 0.8,
     "subject": "a dark rocky asteroid veined with glowing violet rare-metal crystals "
                "and bright metallic specks"},
    {"name": "unknown", "primitive": "rock_b", "strength": 0.8,
     "subject": "a plain grey rocky asteroid, nondescript heavily cratered stone, "
                "no distinctive minerals or colour"},
]


def run_one(spec: dict, in_dir: Path, out_dir: Path, seed: int) -> dict:
    name = spec["name"]
    prompt = compose(spec["subject"], CELESTIAL_STYLE)
    print(f"\n=== {name} (seed={seed}, primitive={spec['primitive']}) ===")
    control = upload_image(SERVER, in_dir / f"{spec['primitive']}_primitive.png")
    graph = build_graph(control, prompt, seed, spec["strength"], prefix=f"asset_harness/{name}")
    pid = queue(SERVER, graph, uuid.uuid4().hex)
    print(f"  prompt_id={pid}; waiting ...")
    hist = wait(SERVER, pid)
    saved = download(SERVER, hist, out_dir)
    rgba = [p for p in saved if "_rgba_" in p.name]
    print(f"  saved {len(saved)} files; rgba={[p.name for p in rgba]}")
    return {"name": name, "prompt": prompt, "seed": seed,
            "rgba": rgba[0].name if rgba else None}


def main() -> None:
    here = Path(__file__).parent
    in_dir = here / "inputs"
    out_dir = here / "outputs" / "celestial"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # (re)generate all needed control primitives
    for prim in {PLANET["primitive"], *(a["primitive"] for a in ASTEROIDS)}:
        make_celestial.PRIMITIVES[prim](in_dir / f"{prim}_primitive.png")

    planet_entry = run_one(PLANET, in_dir, out_dir, BASE_SEED)
    (out_dir / "planet_manifest.json").write_text(json.dumps(
        {"style": CELESTIAL_STYLE, "ships": [planet_entry]}, indent=2))

    asteroid_entries = []
    for i, spec in enumerate(ASTEROIDS):
        # offset the seed per asteroid so shapes vary even when a rock primitive repeats
        asteroid_entries.append(run_one(spec, in_dir, out_dir, BASE_SEED + i + 1))
    (out_dir / "asteroid_manifest.json").write_text(json.dumps(
        {"style": CELESTIAL_STYLE, "ships": asteroid_entries}, indent=2))

    print(f"\nmanifests -> {out_dir/'planet_manifest.json'}, {out_dir/'asteroid_manifest.json'}")


if __name__ == "__main__":
    main()
