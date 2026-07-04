#!/usr/bin/env python3
"""Generate crude ship primitives (ControlNet Canny hints) for a small DWA fleet.

Each is a clean, high-contrast top-down silhouette with internal panel edges — enough for
Canny to give the ControlNet a strong structural signal (angle/scale/part-layout locked).
Distinct silhouettes per ship type so the fleet reads as different vessels.

Usage: python make_primitives.py <hauler|miner|all> [out_dir]
"""
import math
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


def spider_miner(path: Path) -> None:
    """Top-down, RADIALLY SYMMETRIC spider-miner body/head hub (DWA WI 813).

    Not a directional ship: the DWA entity Image is drawn un-rotated (facing comes from the
    procedural legs), so this primitive has NO front — it is mirror-symmetric across both axes
    and 180deg-rotation symmetric (a hexagonal hub, 6-fold, ringed by an 8-fold socket layout).
    Structure = central crusher core (concentric maw + radial teeth), the hexagonal hub, and
    eight leg-root SOCKETS at the rig's `legRootAngle(i) = (i/8)*2pi` positions on the hub edge,
    so the drawn legs land on the art. Clean high-contrast edges for Canny.
    """
    img, d = _canvas()
    cx = cy = W // 2
    n = 8

    hub_r = 300          # hexagonal hub circumradius (centre to vertex)
    socket_ring_r = 300  # sockets centred on the hub edge
    socket_r = 46        # socket radius
    core_r = 150         # crusher core outer radius

    # Hexagonal hub (a hex reads as machined + keeps a symmetric silhouette).
    hexagon = [
        (cx + hub_r * math.cos(math.pi / 6 + k * math.pi / 3),
         cy + hub_r * math.sin(math.pi / 6 + k * math.pi / 3))
        for k in range(6)
    ]
    d.polygon(hexagon, fill=(165, 165, 165), outline=OUTLINE)
    d.line(hexagon + [hexagon[0]], fill=OUTLINE, width=6, joint="curve")

    # Eight leg-root sockets at the exact rig angles, on the hub edge.
    for i in range(n):
        a = (i / n) * 2 * math.pi          # legRootAngle(i)
        sx = cx + socket_ring_r * math.cos(a)
        sy = cy + socket_ring_r * math.sin(a)
        d.ellipse((sx - socket_r, sy - socket_r, sx + socket_r, sy + socket_r),
                  fill=(120, 120, 120), outline=OUTLINE, width=6)
        # inner bore so the socket reads as an attachment point, not a bump
        br = socket_r * 0.45
        d.ellipse((sx - br, sy - br, sx + br, sy + br), fill=(75, 75, 75), outline=OUTLINE, width=3)

    # Crusher core: outer ring, radial teeth, inner maw.
    d.ellipse((cx - core_r, cy - core_r, cx + core_r, cy + core_r),
              fill=(140, 140, 140), outline=OUTLINE, width=6)
    tooth_in, tooth_out = core_r * 0.62, core_r * 0.98
    for k in range(12):
        a = k * (2 * math.pi / 12)
        d.line((cx + tooth_in * math.cos(a), cy + tooth_in * math.sin(a),
                cx + tooth_out * math.cos(a), cy + tooth_out * math.sin(a)),
               fill=OUTLINE, width=5)
    d.ellipse((cx - core_r * 0.55, cy - core_r * 0.55, cx + core_r * 0.55, cy + core_r * 0.55),
              fill=(95, 95, 95), outline=OUTLINE, width=5)
    d.ellipse((cx - core_r * 0.22, cy - core_r * 0.22, cx + core_r * 0.22, cy + core_r * 0.22),
              fill=(60, 60, 60), outline=OUTLINE, width=4)
    img.save(path)
    print(f"wrote {path}")


def leg_segment(path: Path) -> None:
    """One reusable spider-miner LEG SEGMENT (DWA WI 818), drawn horizontally.

    Directional (unlike the radially-symmetric body): a single tapered mechanical limb segment
    that DWA WI 817 stretches along each rig segment (root->knee, knee->tip) and rotates into
    pose. Contract: length axis = +x, proximal joint knuckle at the LEFT (the rotation pivot),
    tapering to a small drill point at the RIGHT; the INNER/tool edge (drill + rock-chainsaw
    teeth) is the BOTTOM, the armored plate is the TOP. Clean high-contrast edges for Canny.
    """
    img, d = _canvas()
    root_x, tip_x, cy = 250, 800, H // 2
    root_half, tip_half = 96, 52

    def half(x: float) -> float:
        t = (x - root_x) / (tip_x - root_x)
        return root_half + (tip_half - root_half) * t

    # Tapered body (top armored edge + bottom tool edge).
    body = [(root_x, cy - root_half), (tip_x, cy - tip_half),
            (tip_x, cy + tip_half), (root_x, cy + root_half)]
    d.polygon(body, fill=(165, 165, 165), outline=OUTLINE)
    d.line(body + [body[0]], fill=OUTLINE, width=6, joint="curve")

    # Proximal joint knuckle (the pivot) + bore.
    d.ellipse((root_x - root_half, cy - root_half, root_x + root_half, cy + root_half),
              fill=(125, 125, 125), outline=OUTLINE, width=6)
    d.ellipse((root_x - 34, cy - 34, root_x + 34, cy + 34), fill=(75, 75, 75), outline=OUTLINE, width=4)

    # Distal drill point.
    d.polygon([(tip_x, cy - tip_half), (tip_x + 150, cy), (tip_x, cy + tip_half)],
              fill=(140, 140, 140), outline=OUTLINE)
    d.line([(tip_x, cy - tip_half), (tip_x + 150, cy), (tip_x, cy + tip_half)], fill=OUTLINE, width=6)

    # Inner tool edge: a row of drill / rock-chainsaw teeth hanging below the bottom edge.
    n_teeth = 9
    for i in range(n_teeth):
        x0 = root_x + (tip_x - root_x) * (i + 0.1) / n_teeth
        x1 = root_x + (tip_x - root_x) * (i + 0.9) / n_teeth
        xm = (x0 + x1) / 2
        base = cy + half(xm)
        d.polygon([(x0, base), (x1, base), (xm, base + 48)], fill=(110, 110, 110), outline=OUTLINE)
        d.line([(x0, base), (xm, base + 48), (x1, base)], fill=OUTLINE, width=4)

    # A couple of panel lines along the armored top edge.
    for f in (0.30, 0.62):
        x = root_x + (tip_x - root_x) * f
        d.line((x, cy - half(x) + 10, x, cy - 12), fill=OUTLINE, width=4)
    img.save(path)
    print(f"wrote {path}")


SHIPS = {"hauler": hauler, "miner": miner, "spider_miner": spider_miner, "leg_segment": leg_segment}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "inputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = SHIPS if which == "all" else {which: SHIPS[which]}
    for name, fn in targets.items():
        fn(out_dir / f"{name}_primitive.png")
