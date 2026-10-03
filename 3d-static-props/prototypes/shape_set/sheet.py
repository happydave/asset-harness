"""A labelled comparison sheet and the bake check.

sheet.py OUT.png ROWLABEL:PREFIX ... -- views front side above
Each row is a prop (render files PREFIX_<view>.png); columns are the views. Prints each row's mean
colour per view over the prop's pixels (alpha > 0), and each row's difference from the first row.
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

out = sys.argv[1]
i = sys.argv.index("--")
rows = [a.split(":", 1) for a in sys.argv[2:i]]
views = sys.argv[i + 1:]
cell, pad, head = 320, 8, 28
W = 150 + len(views) * (cell + pad)
H = head + len(rows) * (cell + pad)
sheet = Image.new("RGB", (W, H), (40, 40, 40))
d = ImageDraw.Draw(sheet)
for c, v in enumerate(views):
    d.text((150 + c * (cell + pad) + 6, 8), v, fill=(255, 255, 255))
means = {}
for r, (label, prefix) in enumerate(rows):
    y = head + r * (cell + pad)
    d.text((6, y + cell // 2), label, fill=(255, 255, 255))
    for c, v in enumerate(views):
        im = Image.open(f"{prefix}_{v}.png").convert("RGBA")
        a = np.asarray(im).astype(float)
        mask = a[..., 3] > 0
        means[(label, v)] = a[mask][:, :3].mean(axis=0)
        bg = Image.new("RGBA", im.size, (90, 90, 90, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB").resize((cell, cell)), (150 + c * (cell + pad), y))
sheet.save(out)
base = rows[0][0]
for label, _ in rows:
    for v in views:
        m = means[(label, v)]
        rel = (m - means[(base, v)]) / np.maximum(means[(base, v)], 1) * 100
        print(f"{label:>14} {v:6} mean RGB {m.round(1)}  vs {base}: {rel.round(1)} %")
