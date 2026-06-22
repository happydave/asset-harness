#!/usr/bin/env python3
"""Derive a smooth grayscale heightmap from an albedo (macro relief only) — PIL, clean.

Luminance carries rough elevation, but a detailed photo's high-frequency detail makes spikes when
displaced, so we keep only the macro signal: autocontrast -> downsample -> upsample -> blur. The
fine detail is left to the albedo/normal, not the geometry. (The heightmap source is pluggable —
swap in a dedicated Z-Image heightmap or a MoGe top-down depth for smoother/more accurate relief.)

    python make_heightmap.py albedo.png height.png [--macro 64] [--blur 12]
"""
import argparse

from PIL import Image, ImageChops, ImageFilter, ImageOps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("albedo")
    ap.add_argument("out")
    ap.add_argument("--macro", type=int, default=64, help="downsample size that sets relief scale")
    ap.add_argument("--blur", type=float, default=12.0)
    ap.add_argument("--highpass", type=float, default=0.0,
                    help="for a DEPTH input (e.g. MoGe top-down depth): subtract a blur of this "
                         "radius to flatten the global near/far tilt, keeping local relief")
    args = ap.parse_args()
    src = Image.open(args.albedo).convert("L")
    h = ImageOps.autocontrast(src)
    if args.highpass > 0:
        low = h.filter(ImageFilter.GaussianBlur(args.highpass))
        h = ImageChops.subtract(h, low, 1.0, 128)  # local relief, centered; drops the global ramp
        h = ImageOps.autocontrast(h).filter(ImageFilter.GaussianBlur(2))
        mode = f"highpass={args.highpass}"
    else:
        h = h.resize((args.macro, args.macro), Image.LANCZOS).resize(src.size, Image.LANCZOS)
        h = h.filter(ImageFilter.GaussianBlur(args.blur))
        mode = f"macro={args.macro}, blur={args.blur}"
    h.save(args.out)
    print(f"heightmap -> {args.out} ({mode})")


if __name__ == "__main__":
    main()
