#!/usr/bin/env python3
"""Generate crude ship primitives (ControlNet Canny hints) for a small DWA fleet.

Each is a clean, high-contrast top-down silhouette with internal panel edges — enough for
Canny to give the ControlNet a strong structural signal (angle/scale/part-layout locked).
Distinct silhouettes per ship type so the fleet reads as different vessels.

Usage: python make_primitives.py <hauler|miner|all> [out_dir]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

W = H = 1024
OUTLINE = (20, 20, 20)


def _canvas():
    img = Image.new("RGB", (W, H), (255, 255, 255))
    return img, ImageDraw.Draw(img)


def hauler(path: Path) -> None:
    """Tall rectangular cargo hull, square side pods, 3-nozzle engine block."""
    img, d = _canvas()
    d.rounded_rectangle((432, 180, 592, 820), radius=40, fill=(170, 170, 170), outline=OUTLINE, width=5)
    d.polygon([(512, 110), (596, 260), (428, 260)], fill=(150, 150, 150), outline=OUTLINE)
    d.line([(512, 110), (596, 260), (428, 260), (512, 110)], fill=OUTLINE, width=5)
    d.ellipse((476, 244, 548, 330), fill=(95, 95, 95), outline=OUTLINE, width=5)
    d.rounded_rectangle((352, 360, 432, 648), radius=20, fill=(140, 140, 140), outline=OUTLINE, width=5)
    d.rounded_rectangle((592, 360, 672, 648), radius=20, fill=(140, 140, 140), outline=OUTLINE, width=5)
    d.rounded_rectangle((396, 776, 628, 884), radius=18, fill=(120, 120, 120), outline=OUTLINE, width=5)
    for x in (452, 512, 572):
        d.ellipse((x - 28, 858, x + 28, 922), fill=(80, 80, 80), outline=OUTLINE, width=5)
    d.line((512, 110, 512, 70), fill=OUTLINE, width=5)
    for y in (380, 470, 560, 660):
        d.line((444, y, 580, y), fill=OUTLINE, width=4)
    img.save(path)
    print(f"wrote {path}")


def miner(path: Path) -> None:
    """Compact body, forward drilling rig (drill head), two round ore tanks, small engine."""
    img, d = _canvas()
    # main body (shorter, rounder)
    d.rounded_rectangle((452, 300, 572, 720), radius=50, fill=(170, 170, 170), outline=OUTLINE, width=5)
    # forward drilling rig: narrowing mount + circular drill head with teeth
    d.polygon([(478, 300), (546, 300), (560, 220), (464, 220)], fill=(140, 140, 140), outline=OUTLINE)
    d.line([(478, 300), (546, 300), (560, 220), (464, 220), (478, 300)], fill=OUTLINE, width=5)
    d.ellipse((462, 120, 562, 232), fill=(110, 110, 110), outline=OUTLINE, width=6)
    d.ellipse((496, 154, 528, 198), fill=(70, 70, 70), outline=OUTLINE, width=4)
    # two round ore tanks on the sides
    d.ellipse((336, 430, 476, 570), fill=(140, 140, 140), outline=OUTLINE, width=5)
    d.ellipse((548, 430, 688, 570), fill=(140, 140, 140), outline=OUTLINE, width=5)
    # cockpit
    d.ellipse((484, 330, 540, 390), fill=(95, 95, 95), outline=OUTLINE, width=5)
    # small engine + two nozzles
    d.rounded_rectangle((456, 712, 568, 776), radius=14, fill=(120, 120, 120), outline=OUTLINE, width=5)
    for x in (492, 532):
        d.ellipse((x - 24, 760, x + 24, 818), fill=(80, 80, 80), outline=OUTLINE, width=5)
    for y in (470, 560, 650):
        d.line((470, y, 554, y), fill=OUTLINE, width=4)
    img.save(path)
    print(f"wrote {path}")


SHIPS = {"hauler": hauler, "miner": miner}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "inputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = SHIPS if which == "all" else {which: SHIPS[which]}
    for name, fn in targets.items():
        fn(out_dir / f"{name}_primitive.png")
