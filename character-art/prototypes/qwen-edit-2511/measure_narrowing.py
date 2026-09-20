#!/usr/bin/env python3
"""WI 1599 — is the residual narrowing global, or is it feature reshaping?

The LoRA's author reports Qwen-2511 "always produced narrow characters" and
prescribes +20% horizontal. Run 2 found the dragonborn's head still narrow
*after* that correction, which could be (a) the global artefact being stronger
than +20%, or (b) the snout genuinely being reshaped. Those have opposite
consequences for the verdict.

Discriminator: measure figure width/height for each subject, source vs the
corrected output's front panel. A ratio that moves by the same factor on the
HUMAN control as on the non-humans is global; a factor that is worse on the
non-humans is feature reshaping.
"""
from PIL import Image
import os

SUBJECTS = ["tiefling", "dragonborn", "halforc", "human"]
PANELS = 5


def subject_bbox(im, step=2, tol=40):
    """Bounding box of the non-background subject, from the corner colour."""
    w, h = im.size
    px = im.convert("RGB").load()
    corner = px[2, 2]
    xs, ys = [], []
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if abs(r - corner[0]) + abs(g - corner[1]) + abs(b - corner[2]) > tol:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def aspect(im):
    bb = subject_bbox(im)
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    return (x1 - x0) / max(1, (y1 - y0))


print("%-11s %8s %8s %8s   %s" % ("subject", "src W/H", "out W/H", "ratio", "reading"))
rows = []
for s in SUBJECTS:
    sp = "inputs/%s.png" % s
    op = "outputs/%s_turnaround_s56_corrected.png" % s
    if not (os.path.exists(sp) and os.path.exists(op)):
        print("%-11s (missing output)" % s); continue
    src = Image.open(sp)
    out = Image.open(op)
    panel = out.crop((0, 0, out.width // PANELS, out.height))  # front view
    a_s, a_o = aspect(src), aspect(panel)
    r = a_o / a_s
    rows.append((s, r))
    print("%-11s %8.4f %8.4f %8.3f" % (s, a_s, a_o, r))

if rows:
    human = dict(rows).get("human")
    print()
    if human:
        print("Human control ratio = %.3f" % human)
        for s, r in rows:
            if s == "human":
                continue
            print("  %-11s %.3f  -> %+.1f%% vs the human control" % (s, r, 100*(r/human - 1)))
        print("\nA non-human within a few %% of the human is the SAME global narrowing.")
        print("A non-human materially below the human is feature-specific reshaping.")
