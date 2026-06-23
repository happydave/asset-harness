#!/usr/bin/env python3
"""Generate crude celestial-body primitives (ControlNet Canny hints) for DWA.

Two subject classes, distinct from the vessel fleet:
  - planet: a large disc with an OFF-CENTRE storm + a few banding arcs. The off-centre
    feature is deliberate — DWA spins the planet about the view axis, and rotation only
    reads if the silhouette/feature is asymmetric (a concentric blob would look static).
  - asteroids: irregular angular rock silhouettes with internal crack edges. A few
    distinct shapes so the per-resource asteroids don't read as clones.

High-contrast on white so Canny gives the ControlNet a strong structural signal.

Usage: python make_celestial.py <name|all> [out_dir]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

W = H = 1024
OUTLINE = (20, 20, 20)
CX = CY = W // 2


def _canvas():
    img = Image.new("RGB", (W, H), (255, 255, 255))
    return img, ImageDraw.Draw(img)


def planet(path: Path) -> None:
    """Large pole-on disc, concentric band arcs, one off-centre cyclonic storm."""
    img, d = _canvas()
    R = 430
    d.ellipse((CX - R, CY - R, CX + R, CY + R), fill=(165, 165, 165), outline=OUTLINE, width=6)
    # concentric banding arcs (cloud bands) — give Canny latitudinal structure
    for rr in (150, 250, 340, 400):
        d.ellipse((CX - rr, CY - rr, CX + rr, CY + rr), outline=OUTLINE, width=3)
    # off-centre cyclonic storm (the asymmetry that makes rotation read)
    sx, sy, sr = CX + 150, CY - 120, 95
    d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(120, 120, 120), outline=OUTLINE, width=5)
    d.ellipse((sx - 45, sy - 45, sx + 45, sy + 45), fill=(95, 95, 95), outline=OUTLINE, width=4)
    img.save(path)
    print(f"wrote {path}")


# A handful of distinct rock silhouettes (angular polygons) + internal crack lines.
_ROCKS = {
    "rock_a": [(330, 470), (430, 300), (610, 280), (740, 430), (720, 640), (560, 740), (370, 690), (300, 560)],
    "rock_b": [(360, 380), (560, 300), (700, 360), (760, 540), (660, 720), (470, 760), (320, 640), (280, 480)],
    "rock_c": [(300, 520), (420, 340), (600, 320), (730, 470), (700, 660), (520, 730), (360, 660)],
}


def _rock(path: Path, pts) -> None:
    img, d = _canvas()
    d.polygon(pts, fill=(165, 165, 165), outline=OUTLINE)
    # thick outline pass (polygon outline width isn't honoured on all Pillow versions)
    d.line(pts + [pts[0]], fill=OUTLINE, width=6, joint="curve")
    # internal facet/crack edges for surface structure
    cx = sum(p[0] for p in pts) // len(pts)
    cy = sum(p[1] for p in pts) // len(pts)
    for i in range(0, len(pts), 2):
        d.line([pts[i], (cx, cy)], fill=OUTLINE, width=3)
    img.save(path)
    print(f"wrote {path}")


def rock_a(path: Path) -> None: _rock(path, _ROCKS["rock_a"])
def rock_b(path: Path) -> None: _rock(path, _ROCKS["rock_b"])
def rock_c(path: Path) -> None: _rock(path, _ROCKS["rock_c"])


PRIMITIVES = {"planet": planet, "rock_a": rock_a, "rock_b": rock_b, "rock_c": rock_c}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "inputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = PRIMITIVES if which == "all" else {which: PRIMITIVES[which]}
    for name, fn in targets.items():
        fn(out_dir / f"{name}_primitive.png")
