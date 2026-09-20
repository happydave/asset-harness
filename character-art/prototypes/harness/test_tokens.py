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
    # The fixture must carry alpha: an RGB source is promoted to alpha 255 everywhere, which makes
    # every polarity assertion below vacuously true rather than failing (WI 1636).
    src = Image.new("RGBA", (600, 1080), (0, 0, 0, 0))
    src.paste((200, 40, 40, 255), (150, 120, 450, 980))
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

        # no baked border: the outermost ring of pixels must not be a drawn frame. Read on the
        # alpha channel rather than on colour -- with a cut-out fixture the edge is transparent, so
        # comparing edge colour against an opaque centre would fail for the wrong reason.
        #
        # Sampled on the left and right columns only. A border encircles the whole perimeter, so
        # any stretch of it that the subject does not occupy is enough to detect one -- and the
        # top row is not such a stretch: the crop biases upward, so the figure reaches it, exactly
        # as a real head-and-shoulders token does.
        im = Image.open(out["foundry_rings"]).convert("RGBA")
        w, h = im.size
        a = im.getchannel("A")
        sides = [a.getpixel((x, y)) for x in (0, w - 1) for y in range(0, h, 16)]
        check("no baked border in ring mode", all(v == 0 for v in sides),
              f"side alpha sample={[v for v in sides if v != 0][:6]}")

        # WI 1636: polarity. The figure is opaque and the background is not -- a token is drawn
        # over a VTT map, so an inverted one renders as the map showing through a coloured tile.
        for name in ("roll20", "foundry_rings"):
            tok = Image.open(out[name]).convert("RGBA")
            ta = tok.getchannel("A")
            tw, th = tok.size
            corners = [ta.getpixel(c) for c in ((0, 0), (tw-1, 0), (0, th-1), (tw-1, th-1))]
            centre_a = ta.getpixel((tw//2, th//2))
            check(f"{name}: background is transparent", all(v == 0 for v in corners), corners)
            check(f"{name}: figure is opaque", centre_a == 255, centre_a)

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
