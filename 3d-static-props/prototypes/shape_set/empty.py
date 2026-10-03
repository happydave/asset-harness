"""The bake's empty share: texels inside the low prop's UV islands still at the marker colour.

empty.py LOW.glb BAKED.png
"""
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw

mesh = trimesh.load(sys.argv[1], force="mesh")
img = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(int)
h, w = img.shape[:2]
uv = mesh.visual.uv
mask = Image.new("L", (w, h), 0)
d = ImageDraw.Draw(mask)
for f in mesh.faces:
    d.polygon([(uv[k][0] * w, (1 - uv[k][1]) * h) for k in f], fill=255)
inside = np.asarray(mask) > 0
marker = (img[..., 0] > 240) & (img[..., 1] < 15) & (img[..., 2] > 240)
print(f"islands {inside.mean() * 100:.1f} % of the texture; marker texels inside them "
      f"{(marker & inside).sum()} of {inside.sum()} = {(marker & inside).sum() / inside.sum() * 100:.2f} %; "
      f"black texels inside {((img.sum(axis=2) < 15) & inside).sum() / inside.sum() * 100:.2f} %")
