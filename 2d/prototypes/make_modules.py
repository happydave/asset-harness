#!/usr/bin/env python3
"""Square-cell station-module primitives for a grid/slot kit (ControlNet Canny hints).

Every module is drawn on the same 1024 cell with connection PORTS centered on its active
edges at identical positions, so any two modules placed in adjacent grid cells mate edge-to-edge.
The ControlNet then locks that footprint + port placement while Z-Image fills in the detail.

Usage: python make_modules.py <name|all> [out_dir]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

W = H = 1024
C = W // 2
MARGIN = 168          # gap from cell edge to module body; the port spans this gap
PORT_HALF = 96        # half-width of an edge port opening
OUTLINE = (20, 20, 20)
BODY = (170, 170, 170)
DARK = (110, 110, 110)
MID = (140, 140, 140)

EDGES = {  # edge -> connector rect (x0,y0,x1,y1) spanning cell-edge..body-edge, centered
    "N": (C - PORT_HALF, 0, C + PORT_HALF, MARGIN),
    "S": (C - PORT_HALF, H - MARGIN, C + PORT_HALF, H),
    "W": (0, C - PORT_HALF, MARGIN, C + PORT_HALF),
    "E": (W - MARGIN, C - PORT_HALF, W, C + PORT_HALF),
}


def _frame(active):
    """Canvas + ports for the given active edges. Returns (img, draw, body_box)."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for e in active:
        d.rectangle(EDGES[e], fill=MID, outline=OUTLINE, width=5)
    # collar bars right at the cell edge (where two modules meet)
    if "N" in active: d.line((C - PORT_HALF, 14, C + PORT_HALF, 14), fill=OUTLINE, width=6)
    if "S" in active: d.line((C - PORT_HALF, H - 14, C + PORT_HALF, H - 14), fill=OUTLINE, width=6)
    if "W" in active: d.line((14, C - PORT_HALF, 14, C + PORT_HALF), fill=OUTLINE, width=6)
    if "E" in active: d.line((W - 14, C - PORT_HALF, W - 14, C + PORT_HALF), fill=OUTLINE, width=6)
    return img, d, (MARGIN, MARGIN, W - MARGIN, H - MARGIN)


def hub(path):
    img, d, b = _frame("NESW")
    d.rounded_rectangle(b, radius=40, fill=BODY, outline=OUTLINE, width=6)
    d.ellipse((C - 150, C - 150, C + 150, C + 150), fill=DARK, outline=OUTLINE, width=6)
    d.ellipse((C - 70, C - 70, C + 70, C + 70), fill=(90, 90, 90), outline=OUTLINE, width=5)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        cx, cy = C + dx * 230, C + dy * 230
        d.rectangle((cx - 45, cy - 45, cx + 45, cy + 45), fill=MID, outline=OUTLINE, width=4)
    img.save(path); print(f"wrote {path}")


def tank(path):
    img, d, b = _frame("NS")           # pass-through segment
    d.rounded_rectangle((300, b[1], 724, b[3]), radius=120, fill=BODY, outline=OUTLINE, width=6)
    for y in (380, 512, 644):
        d.line((300, y, 724, y), fill=OUTLINE, width=5)
    d.ellipse((430, 446, 594, 578), fill=DARK, outline=OUTLINE, width=5)
    img.save(path); print(f"wrote {path}")


def habitat(path):
    img, d, b = _frame("NS")
    d.rounded_rectangle((320, b[1], 704, b[3]), radius=60, fill=BODY, outline=OUTLINE, width=6)
    for y in range(300, 760, 90):       # window rows
        for x in (390, 512, 634):
            d.rectangle((x - 26, y - 18, x + 26, y + 18), fill=(95, 95, 95), outline=OUTLINE, width=4)
    img.save(path); print(f"wrote {path}")


def solar(path):
    img, d, b = _frame("S")            # end module, connects downward
    d.rounded_rectangle((452, 360, 572, b[3]), radius=24, fill=BODY, outline=OUTLINE, width=6)  # spine
    for x0, x1 in ((150, 440), (584, 874)):   # two panel wings
        d.rectangle((x0, 300, x1, 720), fill=MID, outline=OUTLINE, width=6)
        for gx in range(x0, x1, 58):
            d.line((gx, 300, gx, 720), fill=OUTLINE, width=3)
        for gy in range(300, 720, 70):
            d.line((x0, gy, x1, gy), fill=OUTLINE, width=3)
    img.save(path); print(f"wrote {path}")


def dock(path):
    img, d, b = _frame("S")            # connects down; open docking clamp up
    d.rounded_rectangle((b[0], 430, b[2], b[3]), radius=40, fill=BODY, outline=OUTLINE, width=6)
    d.ellipse((C - 160, 150, C + 160, 470), fill=DARK, outline=OUTLINE, width=6)   # docking ring
    d.ellipse((C - 90, 220, C + 90, 400), fill=(255, 255, 255), outline=OUTLINE, width=6)
    for dx in (-200, 200):             # clamps
        d.rectangle((C + dx - 26, 200, C + dx + 26, 360), fill=MID, outline=OUTLINE, width=4)
    img.save(path); print(f"wrote {path}")


MODULES = {"hub": hub, "tank": tank, "habitat": habitat, "solar": solar, "dock": dock}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "inputs")
    out.mkdir(parents=True, exist_ok=True)
    targets = MODULES if which == "all" else {which: MODULES[which]}
    for name, fn in targets.items():
        fn(out / f"module_{name}_primitive.png")
