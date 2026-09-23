#!/usr/bin/env python3
"""Lay renders out in one labelled row, each scaled to the same height.

    side_by_side.py OUT.png "LABEL=path.png" ["LABEL=path.png" ...] [--height 512]
"""
import sys
from PIL import Image, ImageDraw

args = [a for a in sys.argv[1:] if not a.startswith("--")]
height = int(sys.argv[sys.argv.index("--height") + 1]) if "--height" in sys.argv else 512
if "--height" in sys.argv:
    args.remove(str(height))
out, panels = args[0], [a.split("=", 1) for a in args[1:]]
band = 36
tiles = []
for label, path in panels:
    im = Image.open(path).convert("RGB")
    im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    tiles.append((label, im))
sheet = Image.new("RGB", (sum(im.width for _, im in tiles), height + band), (24, 24, 24))
x = 0
draw = ImageDraw.Draw(sheet)
for label, im in tiles:
    sheet.paste(im, (x, band))
    draw.text((x + 8, 10), label, fill=(235, 235, 235))
    x += im.width
sheet.save(out)
print(f"{out}: {sheet.width}x{sheet.height}, {len(tiles)} panels")
