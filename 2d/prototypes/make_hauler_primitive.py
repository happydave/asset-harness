#!/usr/bin/env python3
"""Generate a crude top-down space-hauler primitive to use as a ControlNet hint.

The point is NOT art — it is a clean, high-contrast silhouette with enough internal
edges that Canny gives the ControlNet a strong structural signal (locked angle, scale,
and rough part layout). Z-Image then fills in the actual sci-fi detail.

Usage: python make_hauler_primitive.py [out.png]
"""
import sys
from PIL import Image, ImageDraw

W = H = 1024
CX = W // 2
BG = (255, 255, 255)
OUTLINE = (20, 20, 20)


def draw(out_path: str) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def poly(pts, fill, w=5):
        d.polygon(pts, fill=fill, outline=OUTLINE)
        d.line(pts + [pts[0]], fill=OUTLINE, width=w)

    # main hull (vertical capsule), nose up
    d.rounded_rectangle((432, 180, 592, 820), radius=40, fill=(170, 170, 170), outline=OUTLINE, width=5)
    # nose / forward section
    poly([(512, 110), (596, 260), (428, 260)], (150, 150, 150))
    # cockpit
    d.ellipse((476, 244, 548, 330), fill=(95, 95, 95), outline=OUTLINE, width=5)
    # side cargo pods
    d.rounded_rectangle((352, 360, 432, 648), radius=20, fill=(140, 140, 140), outline=OUTLINE, width=5)
    d.rounded_rectangle((592, 360, 672, 648), radius=20, fill=(140, 140, 140), outline=OUTLINE, width=5)
    # engine block
    d.rounded_rectangle((396, 776, 628, 884), radius=18, fill=(120, 120, 120), outline=OUTLINE, width=5)
    # engine nozzles
    for x in (452, 512, 572):
        d.ellipse((x - 28, 858, x + 28, 922), fill=(80, 80, 80), outline=OUTLINE, width=5)
    # antenna
    d.line((512, 110, 512, 70), fill=OUTLINE, width=5)
    # panel lines across hull
    for y in (380, 470, 560, 660):
        d.line((444, y, 580, y), fill=OUTLINE, width=4)

    img.save(out_path)
    print(f"wrote {out_path} ({W}x{H})")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "inputs/hauler_primitive.png"
    draw(out)
