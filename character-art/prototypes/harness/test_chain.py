#!/usr/bin/env python3
"""Tests for the chain's testable decisions. Plain `python3 test_chain.py`, no pytest."""
import io, sys
from pathlib import Path
from PIL import Image
import chain

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond: FAILS.append(name)

def main():
    print("chain decisions")
    # I4: the inert-detector observable.
    check("identical bytes are inert (a detail pass that changed nothing)",
          chain.is_inert(b"same", b"same") is True)
    check("differing bytes are not inert",
          chain.is_inert(b"before", b"after") is False)
    check("a one-byte difference is enough to be non-inert",
          chain.is_inert(b"a"*1000, b"a"*999 + b"b") is False)
    check("empty vs empty is inert (a stage that produced nothing new)",
          chain.is_inert(b"", b"") is True)

    # The graphs must carry the settings the findings claim, or the findings are wrong.
    g = chain.detail("x.png", chain.FACE_DETECTOR, "p", 1, "pre")
    det = [n for n in g.values() if n["class_type"] == "UltralyticsDetectorProvider"]
    fd = [n for n in g.values() if n["class_type"] == "FaceDetailer"][0]
    check("detail graph provides a bbox detector", len(det) == 1 and det[0]["inputs"]["model_name"] == chain.FACE_DETECTOR)
    check("FaceDetailer is wired to that detector", fd["inputs"]["bbox_detector"][0] in g)
    check("detail graph sets clip skip -2 (silent failure when omitted)",
          any(n["class_type"] == "CLIPSetLastLayer" and n["inputs"]["stop_at_clip_layer"] == -2
              for n in g.values()))
    gen = chain.generate("p", 1, "pre")
    check("generate graph sets clip skip -2",
          any(n["class_type"] == "CLIPSetLastLayer" and n["inputs"]["stop_at_clip_layer"] == -2
              for n in gen.values()))
    hs = chain.house_style("x.png", "p", 1, "pre", 0.25)
    check("house-style loads the finishing checkpoint, not the generation one",
          any(n["class_type"] == "CheckpointLoaderSimple" and n["inputs"]["ckpt_name"] == chain.FINISH_CKPT
              for n in hs.values()))
    check("house-style loads NO LoRA (design D3 defers the house-style LoRA)",
          not any("Lora" in n["class_type"] for n in hs.values()))
    m = chain.matte("x.png", "pre")
    check("matte applies the mask as alpha (RemoveBackground returns a MASK)",
          any(n["class_type"] == "JoinImageWithAlpha" for n in m.values()))

    # WI 1636. A regression guard on the wiring, not evidence of polarity: it would pass unchanged
    # if ComfyUI's mask convention moved. The evidence is figure_is_opaque on a real matte.
    rm = next(k for k, n in m.items() if n["class_type"] == "RemoveBackground")
    inv = [k for k, n in m.items() if n["class_type"] == "InvertMask"]
    join = next(n for n in m.values() if n["class_type"] == "JoinImageWithAlpha")
    check("matte inverts the mask before joining it as alpha", len(inv) == 1, inv)
    check("the inversion reads the background-removal node",
          bool(inv) and m[inv[0]]["inputs"]["mask"][0] == rm)
    check("the join's alpha is the inversion, not the raw removal mask",
          bool(inv) and join["inputs"]["alpha"][0] == inv[0], join["inputs"]["alpha"])

    # --- the polarity predicate -------------------------------------------------------------
    def enc(im):
        b = io.BytesIO(); im.save(b, format="PNG"); return b.getvalue()

    cut = Image.new("RGBA", (400, 700), (0, 0, 0, 0))
    cut.paste((200, 40, 40, 255), (100, 80, 300, 640))
    good = enc(cut)
    flipped = cut.copy(); flipped.putalpha(cut.getchannel("A").point(lambda v: 255 - v))

    check("a figure-opaque cut-out passes", chain.figure_is_opaque(good))
    check("the same image with alpha inverted fails", not chain.figure_is_opaque(enc(flipped)))
    check("a fully opaque image fails (background removal produced nothing)",
          not chain.figure_is_opaque(enc(Image.new("RGBA", (400, 700), (200, 40, 40, 255)))))
    check("an image with no alpha channel fails rather than raising",
          not chain.figure_is_opaque(enc(Image.new("RGB", (400, 700), (200, 40, 40)))))
    check("the predicate does not write", not any(
        Path(n).exists() for n in ("out.png", "matte.png")))
    check("explain_alpha names the assumption it applied",
          "frame edge" in chain.explain_alpha(good), chain.explain_alpha(good))
    check("explain_alpha says so when there is no alpha",
          "no alpha channel" in chain.explain_alpha(enc(Image.new("RGB", (8, 8), (1, 2, 3)))))

    print()
    if FAILS: print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0

if __name__ == "__main__":
    sys.exit(main())
