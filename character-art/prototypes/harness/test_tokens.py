#!/usr/bin/env python3
"""Tests for token export. Plain `python3 test_tokens.py`, no pytest."""
import sys, tempfile
from pathlib import Path
from PIL import Image
import tokens as T, provenance as P

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond: FAILS.append(name)

def main():
    print("token export")
    src = Image.new("RGB", (600, 1080), (200, 40, 40))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = T.export(src, root, "tiefling", ["roll20", "foundry", "foundry_rings"])

        for name, expect_size, expect_fmt in [("roll20",280,"PNG"),("foundry",400,"WEBP"),
                                              ("foundry_rings",512,"WEBP")]:
            im = Image.open(out[name])
            check(f"{name}: {expect_size}x{expect_size}", im.size == (expect_size, expect_size), im.size)
            check(f"{name}: format {expect_fmt}", im.format == expect_fmt, im.format)

        check("ring target meets the 512 floor", Image.open(out["foundry_rings"]).size == (512,512))
        check("no token is written inside masters/",
              all(P.MASTERS_DIR not in Path(p).parts for p in out.values()))

        # no baked border: the outermost ring of pixels must not be a drawn frame. With a flat
        # source, a border would show as an edge colour differing from the interior.
        im = Image.open(out["foundry_rings"]).convert("RGB")
        w, h = im.size
        edge = [im.getpixel((x, 0)) for x in range(0, w, 32)] + [im.getpixel((0, y)) for y in range(0, h, 32)]
        centre = im.getpixel((w//2, h//2))
        check("no baked border in ring mode",
              all(abs(e[0]-centre[0])+abs(e[1]-centre[1])+abs(e[2]-centre[2]) < 30 for e in edge),
              f"edge={edge[:3]} centre={centre}")

        try:
            T.export(src, root, "x", ["roll20", "nosuchvtt"])
            check("unknown target is refused by name", False, "no ValueError")
        except ValueError as e:
            check("unknown target is refused by name", "nosuchvtt" in str(e), str(e))

    print()
    if FAILS: print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0

if __name__ == "__main__":
    sys.exit(main())
