#!/usr/bin/env python3
"""One objective number for axis C: does a route's figures share the plate's light?

Axis C (scene integration) is otherwise judged by looking, and the spike's own Design warned that
looking at four images ranks them on appeal rather than on the axis. This measures the part that
can be measured.

**Warmth** is the mean of (R - B) over a pixel set. A tavern lit by lanterns is strongly positive;
a figure lit frontally on a white portrait backdrop is near zero. So the gap between a figure's
warmth and the surrounding plate's warmth is a direct reading of "was this figure lit by this
room", and the change in that gap across a unify pass is a direct reading of what the pass bought.

It measures one property of four (light colour), and says nothing about shadow, contact or scale.
Reported as one line of evidence, not as the axis.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

import composite
import scene


def warmth(im: Image.Image, box=None) -> float:
    crop = im.crop(box) if box else im
    crop = crop.convert("RGB").resize((crop.width // 8 or 1, crop.height // 8 or 1))
    px = list(crop.getdata())
    return sum(r - b for r, b, in ((p[0], p[2]) for p in px)) / len(px)


def figure_vs_plate(path: Path, boxes: dict) -> dict:
    """Warmth of each figure's torso against the plate strip just above the heads."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    plate = warmth(im, (0, 0, w, round(0.06 * h)))   # ceiling/wall, no figure in it
    out = {"plate": round(plate, 2), "figures": {}}
    for cid, (x0, y0, x1, y1) in boxes.items():
        fh = y1 - y0
        torso = (max(0, x0 + (x1 - x0) // 4), max(0, y0 + round(0.22 * fh)),
                 min(w, x1 - (x1 - x0) // 4), min(h, y0 + round(0.42 * fh)))
        if torso[2] <= torso[0] or torso[3] <= torso[1]:
            continue
        fw = warmth(im, torso)
        out["figures"][cid] = {"warmth": round(fw, 2), "gap": round(fw - plate, 2)}
    gaps = [v["gap"] for v in out["figures"].values()]
    out["mean_abs_gap"] = round(sum(abs(g) for g in gaps) / len(gaps), 2) if gaps else None
    return out


if __name__ == "__main__":
    boxes = json.loads(Path(sys.argv[1]).read_text())
    for p in sys.argv[2:]:
        print(Path(p).name, json.dumps(figure_vs_plate(Path(p), boxes)))
