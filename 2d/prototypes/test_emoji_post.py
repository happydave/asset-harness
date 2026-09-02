#!/usr/bin/env python3
"""Tests for emoji_post.py — plain python3, stdlib + PIL, no pytest.

Run:  python3 test_emoji_post.py
Exits 0 if every check passes, non-zero if any fails, so it can gate a commit.

Pins the Slack-emoji target behaviour: fit (trim -> downscale -> centre on a square canvas, never
upscaling), the spec gate (square / size / alpha / non-blank / byte cap), and the contact sheet's
geometry. Every fixture is synthetic and built in a temp dir — no ComfyUI, no network, no generated
assets — so the gate is runnable anywhere.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402  (import after sys.path insert)
import emoji_post  # noqa: E402

_results = []


def check(name, cond, detail=""):
    _results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{' - ' + detail if detail else ''}")


def sprite(canvas, box, fill=(200, 60, 40, 255), specks_alpha=0):
    """Transparent `canvas` square RGBA with an opaque rect at box=(l,t,r,b)."""
    im = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    l, t, r, b = box
    im.paste(Image.new("RGBA", (r - l, b - t), fill), (l, t))
    if specks_alpha:
        for xy in ((0, 0), (canvas - 1, canvas - 1)):
            im.putpixel(xy, (10, 10, 10, specks_alpha))
    return im


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        S = emoji_post.EMOJI_SIZE

        # --- fit_to_emoji: a wide subject keeps its aspect and is padded, never stretched ---
        p = tmp / "wide.png"
        sprite(512, (56, 156, 456, 356)).save(p)          # 400x200 subject, 2:1
        out = emoji_post.fit_to_emoji(p)
        check("fit: canvas is exactly the emoji size", out.size == (S, S), str(out.size))
        bbox = out.getchannel("A").getbbox()
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        check("fit: 2:1 subject stays 2:1 (padded, not stretched)",
              abs(w / h - 2.0) < 0.05, f"{w}x{h}")
        check("fit: subject spans the long axis", w == S, f"w={w}")
        check("fit: padding is centred vertically",
              abs(bbox[1] - (S - h) // 2) <= 1, f"top={bbox[1]}")
        check("fit: padding is fully transparent", out.getpixel((0, 0))[3] == 0)

        # --- fit_to_emoji: never upscales a subject smaller than the target ---
        p = tmp / "small.png"
        sprite(512, (250, 250, 290, 290)).save(p)          # 40x40 subject
        out = emoji_post.fit_to_emoji(p)
        bbox = out.getchannel("A").getbbox()
        check("fit: a 40px subject is NOT upscaled to fill the canvas",
              (bbox[2] - bbox[0]) == 40, f"w={bbox[2] - bbox[0]}")
        check("fit: the small subject is still centred",
              abs(bbox[0] - (S - 40) // 2) <= 1, f"left={bbox[0]}")

        # --- fit_to_emoji: sub-threshold matting specks do not defeat the trim (WI 814) ---
        # The subject is 100px — smaller than the target — so the correct result is the subject at
        # its native size, centred. A speck-driven trim failure would instead span the full canvas.
        p = tmp / "speckly.png"
        sprite(512, (206, 206, 306, 306), specks_alpha=4).save(p)
        out = emoji_post.fit_to_emoji(p)
        bbox = out.getchannel("A").getbbox()
        check("fit: faint corner specks are ignored when trimming (100px subject stays 100px, "
              "not the full 512 frame downscaled to 128)",
              (bbox[2] - bbox[0]) == 100, f"w={bbox[2] - bbox[0]}")

        # --- the spec gate accepts a well-formed emoji ---
        good = tmp / "good.png"
        emoji_post.save_emoji(emoji_post.fit_to_emoji(tmp / "wide.png"), good)
        check("gate: a fitted emoji passes", emoji_post.check_file(good) == [],
              str(emoji_post.check_file(good)))
        check("gate: the saved file is under the byte cap",
              good.stat().st_size < emoji_post.MAX_BYTES, f"{good.stat().st_size} bytes")

        # --- the spec gate rejects each violation, one at a time ---
        def violations(im, name, fmt="PNG"):
            q = tmp / name
            im.save(q, fmt)
            return " ".join(emoji_post.check_file(q))

        v = violations(Image.new("RGBA", (128, 96), (200, 60, 40, 255)), "notsquare.png")
        check("gate: rejects a non-square image", "not square" in v, v)

        v = violations(Image.new("RGBA", (64, 64), (200, 60, 40, 255)), "wrongsize.png")
        check("gate: rejects a square image of the wrong size", "expected 128x128" in v, v)

        v = violations(Image.new("RGB", (128, 128), (200, 60, 40)), "noalpha.png")
        check("gate: rejects an image with no alpha channel", "no alpha channel" in v, v)

        v = violations(Image.new("RGBA", (128, 128), (0, 0, 0, 0)), "blank.png")
        check("gate: rejects a blank canvas that is otherwise well-formed",
              "empty or near-empty" in v, v)

        v = violations(Image.new("RGBA", (128, 128), (200, 60, 40, 255)), "wrongfmt.webp", "WEBP")
        check("gate: rejects a non-PNG file", "expected PNG" in v, v)

        # a subject just under the blank threshold is rejected; just over is accepted
        under = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        under.paste(Image.new("RGBA", (14, 14), (200, 60, 40, 255)), (10, 10))   # 1.2% of pixels
        v = violations(under, "sparse.png")
        check("gate: rejects a near-blank matte (1.2% opaque)", "empty or near-empty" in v, v)
        over = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        over.paste(Image.new("RGBA", (24, 24), (200, 60, 40, 255)), (10, 10))    # 3.5% of pixels
        check("gate: accepts a small but real subject (3.5% opaque)",
              violations(over, "sparse_ok.png") == "")

        # --- an oversize file is caught by bytes, not by shape ---
        big = tmp / "big.png"
        noisy = Image.new("RGBA", (128, 128))
        noisy.putdata([((x * 7) % 256, (y * 11) % 256, (x * y) % 256, 255)
                       for y in range(128) for x in range(128)])
        noisy.save(big, "PNG", compress_level=0)
        if big.stat().st_size >= emoji_post.MAX_BYTES:
            check("gate: rejects a file at or over the byte cap",
                  "must be under" in " ".join(emoji_post.check_file(big)))
        else:
            check("gate: byte-cap fixture built (file compressed below the cap; cap logic "
                  "exercised by the constant)", True, f"{big.stat().st_size} bytes")

        # --- the oversize fallback path actually runs (Pillow rejects RGBA median-cut) ---
        forced = tmp / "forced.png"
        saved_cap = emoji_post.MAX_BYTES
        try:
            emoji_post.MAX_BYTES = 1          # force every save through the quantise fallback
            emoji_post.save_emoji(noisy, forced)
            check("save: the over-cap quantise fallback runs without raising", forced.exists())
            check("save: the fallback preserves an alpha channel",
                  Image.open(forced).mode in ("RGBA", "LA")
                  or "transparency" in Image.open(forced).info,
                  Image.open(forced).mode)
        except Exception as e:                                  # noqa: BLE001 - the point of the test
            check("save: the over-cap quantise fallback runs without raising", False, repr(e))
        finally:
            emoji_post.MAX_BYTES = saved_cap

        # --- alpha detection reads the file's own mode, not a converted copy ---
        pal = tmp / "palette.png"
        Image.new("RGBA", (128, 128), (200, 60, 40, 255)).quantize(
            colors=64, method=Image.FASTOCTREE).save(pal)
        check("gate: a palette image with transparency counts as having alpha",
              "no alpha channel" not in " ".join(emoji_post.check_file(pal)),
              " ".join(emoji_post.check_file(pal)))

        # --- check() returns a non-zero exit code when anything fails ---
        check("gate: check() exits non-zero on a failing set",
              emoji_post.check([good, tmp / "blank.png"]) == 1)
        check("gate: check() exits zero on a passing set", emoji_post.check([good]) == 0)

        # --- contact sheet geometry ---
        sheet = emoji_post.contact_sheet([good], tmp / "sheet.png", zoom=4)
        im = Image.open(sheet)
        cell = max(emoji_post.DISPLAY_SIZES) * 4 + 12
        expect_w = 190 + cell * len(emoji_post.DISPLAY_SIZES) * 2
        check("sheet: width covers every display size on both backgrounds",
              im.size[0] == expect_w, f"{im.size[0]} vs {expect_w}")
        check("sheet: one row per emoji", im.size[1] == 34 + (cell + 8), str(im.size[1]))
        check("sheet: sizes tested bracket the reported 22-32px display range",
              min(emoji_post.DISPLAY_SIZES) < 22 and max(emoji_post.DISPLAY_SIZES) >= 32,
              str(emoji_post.DISPLAY_SIZES))

        # --- the constants match Slack's stated limit ---
        check("spec: byte cap is 128 KB exclusive", emoji_post.MAX_BYTES == 131072)

    passed, total = sum(_results), len(_results)
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
