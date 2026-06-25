#!/usr/bin/env python3
"""Generate a family of DWA planet variants (WI 619) via the Z-Image ControlNet harness.

Reuses the WI 584 celestial machinery: one shared CELESTIAL_STYLE anchor + the `planet`
control primitive (off-centre storm kept so the in-game spin reads), with a distinct seed
and hue/feature per variant. The set is one art style, eight different worlds — the game
picks one per new game from the world seed.

Emits outputs/planets/planet_variants_manifest.json (build_atlas-compatible: frames
planet-0 .. planet-7).
"""
import json
import uuid
from pathlib import Path

import make_celestial
from generate_celestial import CELESTIAL_STYLE
from run_zimage_controlnet import (build_graph, compose, download, queue,
                                   upload_image, wait)

SERVER = "http://ai2:8188"
BASE_SEED = 729703840979498   # same seed family as the WI 584 celestial set
STRENGTH = 0.85

# Eight worlds: one style, distinct palettes/features. Order is the frame index
# (planet-0 .. planet-7); planet-0 mirrors the original WI 584 blue-grey gas giant.
VARIANTS = [
    "a gas giant viewed pole-on, concentric swirling cloud bands in deep blue-grey and "
    "slate, one large off-centre cyclonic storm, subtle glowing atmospheric rim",
    "a gas giant viewed pole-on, banded clouds in warm rust, amber and ochre, a bright "
    "off-centre storm eye, faint golden atmospheric rim",
    "an icy world viewed pole-on, pale teal and white frozen bands, cracked glacial "
    "surface, an off-centre pale cyclonic swirl, cold cyan rim glow",
    # planet-3: re-rolled — pale/dim violets matte away or read too dark; a saturated body
    # with a bright storm eye holds and pops (final seed recorded in the manifest).
    "a gas giant viewed pole-on, rich saturated royal purple and violet cloud bands, a "
    "bright glowing cyan off-centre storm eye, vivid magenta swirls, deep purple rim",
    # planet-4: re-rolled — pale tan/desert mattes away entirely; a saturated emerald holds.
    "a verdant gas giant viewed pole-on, deep emerald and jade green cloud bands, a dark "
    "off-centre cyclonic storm eye, bright green glowing atmospheric rim",
    "a frozen world viewed pole-on, near-white and pale-blue ice bands, an off-centre "
    "frosted swirl, faint silvery rim glow",
    "a gas giant viewed pole-on, crimson and deep-red cloud bands, a dark off-centre "
    "storm spot, smouldering red atmospheric rim",
    "a gas giant viewed pole-on, indigo and midnight-blue bands, a bright turquoise "
    "off-centre storm, cool luminous rim",
]


def run_one(index: int, subject: str, in_dir: Path, out_dir: Path) -> dict:
    name = f"planet-{index}"
    seed = BASE_SEED + index * 101
    prompt = compose(subject, CELESTIAL_STYLE)
    print(f"\n=== {name} (seed={seed}) ===")
    control = upload_image(SERVER, in_dir / "planet_primitive.png")
    graph = build_graph(control, prompt, seed, STRENGTH, prefix=f"asset_harness/{name}")
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
    out_dir = here / "outputs" / "planets"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    make_celestial.PRIMITIVES["planet"](in_dir / "planet_primitive.png")

    entries = [run_one(i, subj, in_dir, out_dir) for i, subj in enumerate(VARIANTS)]
    (out_dir / "planet_variants_manifest.json").write_text(json.dumps(
        {"style": CELESTIAL_STYLE, "ships": entries}, indent=2))
    print(f"\nmanifest -> {out_dir / 'planet_variants_manifest.json'}  ({len(entries)} variants)")


if __name__ == "__main__":
    main()
