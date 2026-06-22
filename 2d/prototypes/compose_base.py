#!/usr/bin/env python3
"""Compose station modules into a base layout to verify edge ports mate when tiled.

Demo/verification only: places the grid-cell module sprites edge-to-edge on a CELL grid,
rotating each so its port(s) face the hub. Because ports are centered on every cell edge and
all cells are the same size, neighbours line up automatically.

Usage: python compose_base.py [sprites_dir] [out.png]
"""
import sys
from pathlib import Path
from PIL import Image

CELL = 160
# (module, col, row, rotation-degrees) — rotation points the port(s) toward the hub
LAYOUT = [
    ("hub", 1, 1, 0),
    ("solar", 1, 0, 0),      # above: S port faces down into hub N
    ("dock", 1, 2, 180),     # below: rotated so port faces up into hub S
    ("tank", 0, 1, 90),      # left: N/S ports rotated to E/W; E port meets hub W
    ("habitat", 2, 1, 90),   # right: N/S ports rotated to E/W; W port meets hub E
]


def main() -> None:
    sprites = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/station_atlas/sprites")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "outputs/station_atlas/base_layout.png")
    cols = max(c for _, c, _, _ in LAYOUT) + 1
    rows = max(r for _, _, r, _ in LAYOUT) + 1
    canvas = Image.new("RGBA", (cols * CELL, rows * CELL), (12, 14, 20, 255))
    for name, col, row, rot in LAYOUT:
        im = Image.open(sprites / f"{name}.png").convert("RGBA").resize((CELL, CELL), Image.LANCZOS)
        if rot:
            im = im.rotate(rot, expand=False, resample=Image.BICUBIC)
        canvas.alpha_composite(im, (col * CELL, row * CELL))
    canvas.save(out)
    print(f"wrote {out} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
