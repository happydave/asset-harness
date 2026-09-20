#!/usr/bin/env python3
"""Draw an OpenPose skeleton scaffold, rather than extracting one.

Route 3 needs a pose hint placing N figures at chosen positions. The usual way to get one is a
preprocessor custom node run over a reference image -- but there is no reference image for a group
that has never been generated, so extraction would mean generating the very thing the route exists
to control.

Drawing it instead makes the target layout an *input*. This is the design's own technique for
recurring locations ("MLSD control can be drawn rather than derived: a hand-traced two-point
perspective grid gives the model a perspective we chose") applied to figures.

The rendering follows the COCO-18 convention ControlNet's OpenPose models were trained on -- the
same 18 keypoints, the same limb pairs, the same per-limb colours, limbs as alpha-blended rotated
ellipses and joints as solid dots. Matching it matters: an off-distribution scribble would hand
route 3 a handicap that belongs to the drawing rather than to the route.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

# COCO-18: nose, neck, Rsho, Relb, Rwri, Lsho, Lelb, Lwri, Rhip, Rkne, Rank, Lhip, Lkne, Lank,
# Reye, Leye, Rear, Lear
LIMB_SEQ = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10),
            (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]

COLORS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
          (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
          (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]

# A front-facing standing figure, arms at sides -- the pose the cast's masters were generated in.
#
# Both coordinates are fractions of the figure's **own height**, x measured out from its
# centreline. Tying breadth to height rather than to a separate width box is what keeps the
# proportions human: a first cut of this file scaled x by an independent width and produced
# figures with 60 px shoulders on a 650 px body, which no pose model has ever seen.
TEMPLATE = [
    (0.000, 0.055),   # 0  nose
    (0.000, 0.135),   # 1  neck
    (-0.115, 0.170),  # 2  R shoulder
    (-0.135, 0.320),  # 3  R elbow
    (-0.145, 0.460),  # 4  R wrist
    (0.115, 0.170),   # 5  L shoulder
    (0.135, 0.320),   # 6  L elbow
    (0.145, 0.460),   # 7  L wrist
    (-0.058, 0.510),  # 8  R hip
    (-0.062, 0.730),  # 9  R knee
    (-0.065, 0.960),  # 10 R ankle
    (0.058, 0.510),   # 11 L hip
    (0.062, 0.730),   # 12 L knee
    (0.065, 0.960),   # 13 L ankle
    (-0.018, 0.048),  # 14 R eye
    (0.018, 0.048),   # 15 L eye
    (-0.035, 0.055),  # 16 R ear
    (0.035, 0.055),   # 17 L ear
]

# Where the top of every head sits, as a fraction of canvas height.
HEAD_TOP = 0.055


def figure_points(cx: float, height: float, build: float,
                  canvas_w: int, canvas_h: int) -> list[tuple[float, float]]:
    """Place the template as one figure.

    `cx` is the centreline as a canvas-width fraction, `height` the figure's full height as a
    canvas-height fraction (which may exceed 1.0 -- see PARTY_LAYOUT), and `build` a breadth
    multiplier so a heavy character is heavy rather than merely tall.
    """
    h = height * canvas_h
    top = HEAD_TOP * canvas_h
    return [(cx * canvas_w + dx * build * h, top + dy * h) for dx, dy in TEMPLATE]


def _ellipse_poly(p1, p2, width: float) -> list[tuple[float, float]]:
    """The limb shape cv2.ellipse2Poly produces in the reference renderer: an ellipse whose major
    axis spans the two joints."""
    cx, cy = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    dx, dy = p1[0] - p2[0], p1[1] - p2[1]
    a = math.hypot(dx, dy) / 2
    b = width / 2
    ang = math.atan2(dy, dx)
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(0, 360, 10):
        t = math.radians(i)
        ex, ey = a * math.cos(t), b * math.sin(t)
        pts.append((cx + ex * ca - ey * sa, cy + ex * sa + ey * ca))
    return pts


def render(figures: list[list[tuple[float, float]]], canvas_w: int, canvas_h: int) -> Image.Image:
    """Render all figures onto one black canvas."""
    base = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    stick = max(4, round(canvas_h / 120))
    dot = max(4, round(canvas_h / 140))

    # Limbs first, alpha-blended at 0.6 as the reference renderer does, so crossings read as
    # crossings rather than as whichever limb was drawn last.
    limbs = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    ld = ImageDraw.Draw(limbs)
    for pts in figures:
        for i, (a, b) in enumerate(LIMB_SEQ):
            ld.polygon(_ellipse_poly(pts[a], pts[b], stick), fill=COLORS[i])
    base = Image.blend(base, limbs, 0.6)

    d = ImageDraw.Draw(base)
    for pts in figures:
        for i, (x, y) in enumerate(pts):
            d.ellipse((x - dot, y - dot, x + dot, y + dot), fill=COLORS[i])
    return base


def party_scaffold(canvas_w: int, canvas_h: int, layout) -> Image.Image:
    """`layout` is one (cx, height, build) per figure, left to right."""
    figs = [figure_points(cx, h, b, canvas_w, canvas_h) for cx, h, b in layout]
    return render(figs, canvas_w, canvas_h)


# Heights exceed 1.0 on purpose: the legs run off the bottom and the framing lands just below the
# knee. That is WI 1599's pixel-budget lesson applied -- a full-body party shot on this canvas
# gives each head about 100 px and a tusk about six, which is the resolution at which that spike's
# contact sheet nearly picked the worst half-orc in the set. Cropping to knee-up roughly doubles
# the pixels on the features every route is scored on.
#
# The heights are also bounded from above, and that bound is geometry rather than taste: shoulder
# span is about 0.23 of a figure's height, so four figures on a 1344 px canvas cannot be taller
# than ~1.3 canvas heights without their shoulders colliding and the outer two losing an arm off
# the frame edge. The first cut of this layout did exactly that.
#
# Heights and builds differ because the cast does; four identical bipeds would make the layout
# check easier than the real case.
PARTY_LAYOUT = [
    (0.150, 1.28, 1.14),   # half-orc  -- tallest, broadest
    (0.383, 1.18, 0.92),   # tiefling  -- slightest
    (0.617, 1.23, 1.00),   # human
    (0.850, 1.26, 1.08),   # dragonborn
]


if __name__ == "__main__":
    import sys
    w, h = int(sys.argv[1]), int(sys.argv[2])
    party_scaffold(w, h, PARTY_LAYOUT).save(sys.argv[3])
    print(f"wrote {sys.argv[3]} ({w}x{h}, {len(PARTY_LAYOUT)} figures)")
