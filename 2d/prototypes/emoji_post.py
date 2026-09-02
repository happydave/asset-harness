#!/usr/bin/env python3
"""Turn generated RGBA candidates into Slack-ready emoji, and gate them against the target spec.

Three steps, deliberately separable:

  build  — trim to the alpha bbox, scale DOWN to fit, centre on a square transparent canvas, save PNG
  check  — assert every file satisfies the Slack emoji spec; non-zero exit if any does not
  sheet  — render the candidates at DISPLAY sizes on light and dark, for a human/agent to judge

The spec is documented in ../../docs/delivery-targets/slack-emoji.md. The numbers here are that
document's, not folklore: Slack states "square images under 128KB … work best" and publishes no pixel
dimension, so 128x128 is a convention we adopt and the byte cap is a real limit.

The reason `sheet` exists at all: an emoji is displayed at roughly a fifth of the size it is stored
at, so "it looks good" at 128 px says almost nothing about whether it works. Judge it small.

Stdlib + PIL only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from build_atlas import trim_and_fit  # trim to alpha bbox + LANCZOS downscale (WI 814 speck guard)

EMOJI_SIZE = 128
MAX_BYTES = 128 * 1024          # Slack: "under 128KB"; 131072 bytes, exclusive
ALPHA_THRESHOLD = 8             # ignore sub-threshold matting specks when trimming
MIN_OPAQUE_FRACTION = 0.02      # a matte that kept almost nothing is a failure, not an emoji

# Display sizes to judge against. Slack publishes NO display size; these bracket the commonly
# reported 22-32 px and add a pessimistic case. They are a test range, not a Slack fact.
DISPLAY_SIZES = (16, 22, 32)
LIGHT_BG = (248, 248, 248)
DARK_BG = (26, 29, 33)


def opaque_fraction(im: Image.Image) -> float:
    """Fraction of pixels that are more opaque than the speck threshold."""
    hist = im.convert("RGBA").getchannel("A").histogram()
    return sum(hist[ALPHA_THRESHOLD:]) / max(1, sum(hist))


def fit_to_emoji(src: Path, size: int = EMOJI_SIZE) -> Image.Image:
    """Trim to content, scale down to fit, centre on a square fully-transparent canvas.

    Never upscales: `trim_and_fit` only resizes when the subject is larger than the target, so a
    subject already smaller than `size` is centred at its native resolution rather than invented into
    more detail than it has.
    """
    fitted = trim_and_fit(src, size, alpha_threshold=ALPHA_THRESHOLD)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    w, h = fitted.size
    canvas.paste(fitted, ((size - w) // 2, (size - h) // 2))
    return canvas


def save_emoji(im: Image.Image, dest: Path) -> Path:
    """Save as PNG under the byte cap, escalating compression only if needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG", optimize=True)
    if dest.stat().st_size >= MAX_BYTES:
        # Palette-quantise as the fallback. FASTOCTREE, not MEDIANCUT: Pillow's median-cut path
        # rejects RGBA, so the obvious-looking call would raise exactly when this branch is needed.
        im.convert("RGBA").quantize(colors=255, method=Image.FASTOCTREE).save(
            dest, "PNG", optimize=True)
    return dest


def check_file(path: Path) -> list[str]:
    """Return a list of spec violations for one file; empty means it passes."""
    problems: list[str] = []
    try:
        im = Image.open(path)
    except Exception as e:                                     # noqa: BLE001 - report, don't raise
        return [f"unreadable: {e}"]
    if im.format != "PNG":
        problems.append(f"format is {im.format}, expected PNG")
    if getattr(im, "n_frames", 1) != 1:
        problems.append(f"{im.n_frames} frames, expected a single static frame (not an APNG)")
    w, h = im.size
    if w != h:
        problems.append(f"{w}x{h} is not square")
    if (w, h) != (EMOJI_SIZE, EMOJI_SIZE):
        problems.append(f"{w}x{h}, expected {EMOJI_SIZE}x{EMOJI_SIZE}")
    # Ask the FILE, not a converted copy: `im.convert("RGBA")` always reports an alpha band, so
    # testing that would be a check that can never fail.
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if not has_alpha:
        problems.append(f"mode {im.mode} carries no alpha channel")
    frac = opaque_fraction(im)
    if frac < MIN_OPAQUE_FRACTION:
        problems.append(f"alpha is empty or near-empty ({frac:.3%} opaque) — a blank canvas")
    size = path.stat().st_size
    if size >= MAX_BYTES:
        problems.append(f"{size} bytes, must be under {MAX_BYTES}")
    return problems


def check(paths: list[Path]) -> int:
    """Gate: print a per-file verdict, return a process exit code."""
    failed = 0
    for p in sorted(paths):
        problems = check_file(p)
        if problems:
            failed += 1
            print(f"FAIL {p.name}")
            for pr in problems:
                print(f"       - {pr}")
        else:
            print(f"ok   {p.name}  ({p.stat().st_size} bytes, {opaque_fraction(Image.open(p)):.1%} opaque)")
    print(f"\n{len(paths) - failed}/{len(paths)} pass the Slack emoji spec")
    return 1 if failed else 0


def contact_sheet(paths: list[Path], dest: Path, zoom: int = 5) -> Path:
    """One row per emoji: its name, then each display size rendered on light and on dark.

    Each cell is the emoji downscaled to the true display size and then magnified with NEAREST, so
    what is inspected is genuinely the pixels Slack would show — magnified, not re-rendered.
    """
    paths = sorted(paths)
    label_w = 190
    cell = max(DISPLAY_SIZES) * zoom + 12
    row_h = cell + 8
    width = label_w + cell * len(DISPLAY_SIZES) * 2
    height = 34 + row_h * len(paths)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)

    x = label_w
    for bg_name in ("light", "dark"):
        for s in DISPLAY_SIZES:
            draw.text((x + 6, 10), f"{s}px {bg_name}", fill=(0, 0, 0))
            x += cell
    draw.line([(0, 30), (width, 30)], fill=(200, 200, 200))

    for row, p in enumerate(paths):
        y = 34 + row * row_h
        draw.text((6, y + cell // 2 - 4), p.stem[:28], fill=(0, 0, 0))
        im = Image.open(p).convert("RGBA")
        x = label_w
        for bg in (LIGHT_BG, DARK_BG):
            for s in DISPLAY_SIZES:
                small = im.resize((s, s), Image.LANCZOS)
                plate = Image.new("RGBA", (s, s), bg + (255,))
                plate = Image.alpha_composite(plate, small)
                big = plate.convert("RGB").resize((s * zoom, s * zoom), Image.NEAREST)
                sheet.paste(big, (x + 6, y + (cell - s * zoom) // 2))
                x += cell
        draw.line([(0, y + row_h - 4), (width, y + row_h - 4)], fill=(235, 235, 235))

    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return dest


def _pngs(args_paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args_paths:
        p = Path(a)
        out.extend(sorted(q for q in p.glob("*.png") if not q.stem.endswith("_opaque"))
                   if p.is_dir() else [p])
    if not out:
        raise SystemExit("no PNGs found")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="fit candidates to the Slack emoji target")
    b.add_argument("paths", nargs="+", help="RGBA PNGs or directories of them")
    b.add_argument("--out", required=True, help="output directory")
    b.add_argument("--size", type=int, default=EMOJI_SIZE)

    c = sub.add_parser("check", help="gate files against the Slack emoji spec")
    c.add_argument("paths", nargs="+")

    s = sub.add_parser("sheet", help="render a display-size legibility contact sheet")
    s.add_argument("paths", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--zoom", type=int, default=5)

    args = ap.parse_args()
    paths = _pngs(args.paths)

    if args.cmd == "build":
        out = Path(args.out)
        for p in paths:
            dest = save_emoji(fit_to_emoji(p, args.size), out / p.name)
            print(f"{p.name} -> {dest} ({dest.stat().st_size} bytes)")
    elif args.cmd == "check":
        sys.exit(check(paths))
    else:
        print(contact_sheet(paths, Path(args.out), args.zoom))


if __name__ == "__main__":
    main()
