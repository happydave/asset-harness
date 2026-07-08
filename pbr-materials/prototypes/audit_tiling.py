#!/usr/bin/env python3
"""Multi-scale tiling audit for library material sets (WI 871).

For each named set under outputs/library/, emit an 8x8 tiled albedo sheet downsampled to
inspection size (the derivation already emits a 3x3 preview) and a per-set audit strip
combining 1x / 3x3 / 8x8 side by side. Tiling artifacts show up as seams (edge heal failure)
or a repeating "grid beat" (a dominant composition) — visible at 8x8 when invisible at 1x.

Also verifies the delivered 4-map contract when given --check-dir: for every named set the
four contract maps exist (<name>_{albedo,normal,metallic_roughness,occlusion}.png), are the
expected size, and decode as RGB.

Run: python audit_tiling.py grass steppe ...          (audit named sets)
     python audit_tiling.py --check-dir <dir> grass ... (contract check a delivery directory)
Outputs land next to each set (audit strip) and in outputs/library/audit/ (contact sheet).
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

INSPECT = 512  # each audit panel is INSPECT x INSPECT
CONTRACT_MAPS = ("albedo", "normal", "metallic_roughness", "occlusion")
CONTRACT_SIZE = 1024


def tiled(img: Image.Image, n: int) -> Image.Image:
    w, h = img.size
    sheet = Image.new("RGB", (w * n, h * n))
    for i in range(n):
        for j in range(n):
            sheet.paste(img, (i * w, j * h))
    return sheet.resize((INSPECT, INSPECT), Image.LANCZOS)


def audit_set(lib: Path, name: str) -> Image.Image:
    albedo = Image.open(lib / name / f"{name}_albedo.png").convert("RGB")
    panels = [albedo.resize((INSPECT, INSPECT), Image.LANCZOS), tiled(albedo, 3), tiled(albedo, 8)]
    strip = Image.new("RGB", (INSPECT * 3 + 8 * 2, INSPECT), (24, 24, 24))
    for k, p in enumerate(panels):
        strip.paste(p, (k * (INSPECT + 8), 0))
    strip.save(lib / name / f"{name}_tiling_audit.png")
    (lib / name / f"{name}_tiled_8x8.png").parent.mkdir(exist_ok=True)
    tiled(albedo, 8).save(lib / name / f"{name}_tiled_8x8.png")
    return strip


def check_contract(check_dir: Path, names: list[str]) -> int:
    failures = 0
    for name in names:
        for m in CONTRACT_MAPS:
            p = check_dir / f"{name}_{m}.png"
            if not p.exists():
                print(f"FAIL missing: {p}")
                failures += 1
                continue
            img = Image.open(p)
            if img.size != (CONTRACT_SIZE, CONTRACT_SIZE):
                print(f"FAIL size {img.size}: {p}")
                failures += 1
            img.convert("RGB")  # decodable
    print(f"contract check: {len(names)} sets x {len(CONTRACT_MAPS)} maps, {failures} failure(s)")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--check-dir", type=Path, default=None,
                    help="verify the 4-map contract in this delivery directory instead of auditing")
    args = ap.parse_args()
    if args.check_dir:
        sys.exit(1 if check_contract(args.check_dir, args.names) else 0)

    lib = Path(__file__).parent / "outputs" / "library"
    strips = [(n, audit_set(lib, n)) for n in args.names]
    # contact sheet: one labelled audit strip per row (1x | 3x3 | 8x8)
    pad, label_h = 8, 24
    row_h = INSPECT + label_h + pad
    sheet = Image.new("RGB", (strips[0][1].width, row_h * len(strips)), (24, 24, 24))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(sheet)
    for r, (name, strip) in enumerate(strips):
        draw.text((4, r * row_h + 4), f"{name}   (1x | 3x3 | 8x8)", fill=(230, 230, 230))
        sheet.paste(strip, (0, r * row_h + label_h))
    out = lib / "audit"
    out.mkdir(exist_ok=True)
    sheet.save(out / "tiling_contact_sheet.png")
    print(f"audit -> {out / 'tiling_contact_sheet.png'} + per-set strips")


if __name__ == "__main__":
    main()
