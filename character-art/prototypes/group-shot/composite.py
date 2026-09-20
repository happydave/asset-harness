#!/usr/bin/env python3
"""Route 2's assembly, the figure masks route 3 needs, and the one placement rule both obey.

`place()` is the single source of truth for where each character goes. Route 2 pastes mattes with
it, route 3 pastes mattes with it, the masks are cut with it and the head crops are taken from it
-- so every route is aiming at the same target and their layout scores are comparable. Two copies
of this arithmetic would be two different targets wearing one name.

Compositing is deliberately plain: trim each matte to its own content, scale to the figure height
the layout asks for, paste with the head on the same line the scaffold uses. No colour matching,
no shadow, no edge treatment. The unify pass is the route's answer to those, and pre-correcting by
hand would measure the hand rather than the route.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

import pose
import scene


def load_cutout(path: Path) -> Image.Image:
    """Load a matte as a figure-opaque RGBA cut-out, trimmed to the figure.

    WI 1611's mattes are **alpha-inverted**: the figure is the transparent hole and the background
    is opaque, so compositing one pastes a character-shaped piece of white. The polarity is read
    from the image rather than assumed, because this spike should keep working whichever way the
    upstream defect is eventually resolved -- and because silently inverting everything would hide
    a correct matte the day one arrives. An inversion is announced, not performed quietly.
    """
    img = Image.open(path).convert("RGBA")
    a = img.getchannel("A")
    w, h = img.size
    corners = [a.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if sum(corners) / 4 > 128:
        print(f"  [matte] {path.name}: corners opaque -> inverting alpha (WI 1611 defect)")
        img.putalpha(a.point(lambda v: 255 - v))
    return _trim(img)


def _trim(img: Image.Image) -> Image.Image:
    """Crop an RGBA cut-out to its own visible content, so 'figure height' means the figure and
    not the transparent margin the matte inherited from its portrait canvas."""
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def place(cid: str, cut_w: int, cut_h: int,
          canvas=(scene.SCORE_W, scene.SCORE_H)) -> tuple[int, int, int, int]:
    """Where a figure of the given aspect goes on the canvas: (left, top, right, bottom).

    The box may extend past the bottom edge -- that is the knee-up framing, not an error.
    """
    cw, ch = canvas
    idx = [f.cid for f in scene.CAST].index(cid)
    cx, height, _build = pose.PARTY_LAYOUT[idx]

    target_h = round(height * ch)
    target_w = round(cut_w * target_h / cut_h)
    left = round(cx * cw - target_w / 2)
    top = round(pose.HEAD_TOP * ch)
    return (left, top, left + target_w, top + target_h)


def paste_cast(base: Image.Image, matte_paths: dict[str, Path],
               canvas=(scene.SCORE_W, scene.SCORE_H)) -> dict[str, tuple[int, int, int, int]]:
    """Paste every character's cut-out onto `base` (RGBA, modified in place). Returns placed boxes.

    `paste` rather than `alpha_composite` because the figures deliberately run off the bottom edge
    and only `paste` clips instead of raising.
    """
    boxes = {}
    for f in scene.CAST:
        cut = load_cutout(matte_paths[f.cid])
        box = place(f.cid, cut.width, cut.height, canvas)
        cut = cut.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        base.paste(cut, (box[0], box[1]), cut)
        boxes[f.cid] = box
    return boxes


def build(backdrop_path: Path, matte_paths: dict[str, Path], out_path: Path,
          canvas=(scene.SCORE_W, scene.SCORE_H)) -> dict[str, tuple[int, int, int, int]]:
    """Route 2: the cast over an environment plate, and nothing else."""
    base = Image.open(backdrop_path).convert("RGBA").resize(canvas, Image.LANCZOS)
    boxes = paste_cast(base, matte_paths, canvas)
    base.convert("RGB").save(out_path)
    return boxes


def write_masks(boxes: dict[str, tuple[int, int, int, int]], out_dir: Path,
                canvas=(scene.SCORE_W, scene.SCORE_H), pad: int = 24) -> dict[str, Path]:
    """One white-on-black rectangle per figure, padded so an inpaint can work on the seam between
    the figure and the plate rather than stopping exactly at it."""
    cw, ch = canvas
    paths = {}
    for cid, (x0, y0, x1, y1) in boxes.items():
        m = Image.new("RGB", (cw, ch), (0, 0, 0))
        m.paste((255, 255, 255), (max(0, x0 - pad), max(0, y0 - pad),
                                  min(cw, x1 + pad), min(ch, y1 + pad)))
        p = out_dir / f"mask_{cid}.png"
        m.save(p)
        paths[cid] = p
    return paths


def head_band(canvas=(scene.SCORE_W, scene.SCORE_H), frac: float = 0.42) -> tuple[int, int, int, int]:
    """The crop every route's identity judgement is made from (spike.md FC4): the full width of
    the canvas, top `frac` of its height, at full resolution.

    Route-neutral on purpose. A layout-derived per-figure window is only correct for the routes
    that control layout -- applied to route 1 it would crop empty tavern and score a head that was
    never in the box, which would flatter the controlled routes for the wrong reason. A detector
    would be route-neutral but would make the comparison partly about the detector, and the only
    one installed is anime-face tuned with a hit rate on non-human heads established at n=1
    (WI 1611 F-t3). A fixed strip is the honest instrument: every route was asked for standing
    figures, so every route's heads are in it or the route failed.
    """
    cw, ch = canvas
    return (0, 0, cw, round(frac * ch))


def figure_head_window(cid: str, boxes: dict[str, tuple[int, int, int, int]],
                       canvas=(scene.SCORE_W, scene.SCORE_H)) -> tuple[int, int, int, int]:
    """A tighter per-figure head crop, for the routes whose figure boxes are actually known
    (2 and 3, which paste). Clamped to the canvas."""
    cw, ch = canvas
    x0, y0, x1, y1 = boxes[cid]
    fh = y1 - y0
    cx = (x0 + x1) / 2
    half = 0.105 * fh
    ccy = y0 + 0.070 * fh
    return (max(0, round(cx - half)), max(0, round(ccy - half)),
            min(cw, round(cx + half)), min(ch, round(ccy + half)))
