#!/usr/bin/env python3
"""Turn a scored image into the two things a judgement is actually made from.

`view`  — the whole frame at a size a reader can take in, for axis B (layout) and axis C (scene
          integration), both of which are properties of the composition rather than of a face.
`band`  — the top 42 % of the frame at **full resolution**, for axis A (identity).

The split exists because of a specific failure. WI 1599's contact sheet nearly selected the worst
half-orc in its set: that figure stood further back, so its tusks had the fewest pixels, and at
sheet scale "fewest pixels" reads as "smooth". A whole-frame view of a group shot is a contact
sheet by another name, and the features under test here are a tusk pair and a snout.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import composite
import scene

VIEW_W = 1200


def view(src: Path, dest: Path) -> None:
    im = Image.open(src)
    im.resize((VIEW_W, round(im.height * VIEW_W / im.width)), Image.LANCZOS).save(dest)


def band(src: Path, dest: Path, half: str | None = None) -> None:
    """The head strip at native resolution. `half` splits it left/right, which doubles the pixels
    on each face when the strip is looked at."""
    im = Image.open(src)
    x0, y0, x1, y1 = composite.head_band((im.width, im.height))
    if half == "l":
        x1 = im.width // 2
    elif half == "r":
        x0 = im.width // 2
    im.crop((x0, y0, x1, y1)).save(dest)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for src in sys.argv[2:]:
        p = Path(src)
        stem = f"{p.parent.name}_{p.stem}"
        view(p, out / f"{stem}__view.png")
        band(p, out / f"{stem}__band_l.png", "l")
        band(p, out / f"{stem}__band_r.png", "r")
        print(f"{stem}: view + 2 bands")


if __name__ == "__main__":
    main()
