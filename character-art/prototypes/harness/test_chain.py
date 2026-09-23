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

    def enc(im, text=None):
        """PNG bytes; `text` becomes a `tEXt` chunk named `prompt`, as ComfyUI's SaveImage writes."""
        b = io.BytesIO()
        info = None
        if text is not None:
            from PIL.PngImagePlugin import PngInfo
            info = PngInfo(); info.add_text("prompt", text)
        im.save(b, format="PNG", pnginfo=info)
        return b.getvalue()

    # I4: the inert-detector observable is the *pixels* (WI 1732). The fixtures carry real tEXt
    # chunks, because a stage's embedded graph is exactly what differs between an inert pass's
    # input and output.
    pic = Image.new("RGB", (64, 96), (10, 20, 30))
    pic.putpixel((5, 5), (200, 200, 200))
    same_pixels_a = enc(pic, '{"1": {"class_type": "LoadImage"}}')
    same_pixels_b = enc(pic, '{"1": {"class_type": "LoadImage"}, "7": {"class_type": "FaceDetailer"}}')
    check("fixture: the two files really differ in bytes", same_pixels_a != same_pixels_b)
    check("identical pixels with different embedded graphs are inert",
          chain.is_inert(same_pixels_a, same_pixels_b) is True)
    check("identical bytes are inert", chain.is_inert(same_pixels_a, same_pixels_a) is True)
    moved = pic.copy(); moved.putpixel((6, 5), (201, 200, 200))
    check("a one-pixel difference is not inert", chain.is_inert(same_pixels_a, enc(moved)) is False)
    solid = Image.new("RGB", (64, 96), (9, 9, 9))
    raw = bytes(range(64)) * 96
    l_img = Image.frombytes("L", (64, 96), raw)
    p_img = Image.frombytes("P", (64, 96), raw); p_img.putpalette([0, 0, 0] * 256)
    check("fixture: L and P carry identical raw bytes", l_img.tobytes() == p_img.tobytes())
    check("same raw bytes in different modes is not inert (mode is compared, not only bytes)",
          chain.is_inert(enc(l_img), enc(p_img)) is False)
    check("same bytes at a transposed size is not inert (size is compared, not only bytes)",
          chain.is_inert(enc(solid), enc(solid.transpose(Image.Transpose.ROTATE_90))) is False)
    check("same pixels, RGB vs RGBA, is not inert (an added channel is a change)",
          chain.is_inert(same_pixels_a, enc(pic.convert("RGBA"))) is False)
    try:
        chain.is_inert(same_pixels_a, b"not a png at all")
        check("non-image bytes raise rather than judging", False, "no ValueError")
    except ValueError as e:
        check("non-image bytes raise rather than judging", "not a decodable image" in str(e), str(e))

    # The detector's mask: any pixel above zero means it found something.
    zero = Image.new("RGB", (64, 96), (0, 0, 0))
    check("an all-zero mask means nothing detected", chain.mask_detected(enc(zero)) is False)
    one = zero.copy(); one.putpixel((30, 40), (255, 255, 255))
    check("a single lit pixel means detected", chain.mask_detected(enc(one)) is True)

    # The verdict: four cells, three outcomes, each reason naming its case.
    v = chain.detail_verdict
    check("detected + changed -> pass", v(True, True).outcome == "pass")
    check("not detected + unchanged -> skip", v(False, False).outcome == "skip"
          and "found nothing" in v(False, False).reason)
    check("detected + unchanged -> fail (inert, I4)", v(True, False).outcome == "fail"
          and "inert" in v(True, False).reason)
    check("not detected + changed -> fail (not a detail pass)", v(False, True).outcome == "fail"
          and "found nothing yet the pixels changed" in v(False, True).reason)

    # The embedded recipe a master carries.
    graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
             "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "1boy, tusks", "clip": ["2", 0]}},
             "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad", "clip": ["2", 0]}},
             "6": {"class_type": "KSampler", "inputs": {"seed": 202, "positive": ["3", 0],
                                                       "negative": ["4", 0]}}}
    import json as _json
    rec = chain.embedded_recipe(enc(pic, _json.dumps(graph)))
    check("embedded recipe reads the KSampler seed, the positive and the negative prompt",
          rec == {"seed": 202, "prompt": "1boy, tusks", "negative": "bad"}, rec)
    one_sided = {k: v for k, v in graph.items() if k != "4"}
    one_sided["6"] = {"class_type": "KSampler", "inputs": {"seed": 202, "positive": ["3", 0]}}
    rec = chain.embedded_recipe(enc(pic, _json.dumps(one_sided)))
    check("a KSampler with no negative link reads negative None, not a guess",
          rec == {"seed": 202, "prompt": "1boy, tusks", "negative": None}, rec)

    def neg_of(g):
        ks = next(n for n in g.values() if n["class_type"] == "KSampler")["inputs"]
        return g[str(ks["negative"][0])]["inputs"]["text"]
    check("generate uses the negative it is given",
          neg_of(chain.generate("p", 1, "x", negative="no hats")) == "no hats")
    check("generate defaults the negative to NEG", neg_of(chain.generate("p", 1, "x")) == chain.NEG)
    # The roster's negative keys the master only; the finishing passes always use NEG (README).
    def neg_into(g, cls):
        node = next(n for n in g.values() if n["class_type"] == cls)["inputs"]
        return g[str(node["negative"][0])]["inputs"]["text"]
    check("the detail pass uses the finishing negative NEG",
          neg_into(chain.detail("x.png", chain.FACE_DETECTOR, "p", 1, "pre"), "FaceDetailer") == chain.NEG)
    check("the house-style pass uses the finishing negative NEG",
          neg_into(chain.house_style("x.png", "p", 1, "pre", 0.3), "KSampler") == chain.NEG)
    check("a PNG with no prompt chunk has no recipe (provenance absent)",
          chain.embedded_recipe(enc(pic)) is None)
    check("a prompt chunk with no KSampler has no recipe",
          chain.embedded_recipe(enc(pic, '{"1": {"class_type": "LoadImage", "inputs": {}}}')) is None)

    # The graphs must carry the settings the findings claim, or the findings are wrong.
    g = chain.detail("x.png", chain.FACE_DETECTOR, "p", 1, "pre")
    det = [n for n in g.values() if n["class_type"] == "UltralyticsDetectorProvider"]
    fd = [n for n in g.values() if n["class_type"] == "FaceDetailer"][0]
    check("detail graph provides a bbox detector", len(det) == 1 and det[0]["inputs"]["model_name"] == chain.FACE_DETECTOR)
    check("FaceDetailer is wired to that detector", fd["inputs"]["bbox_detector"][0] in g)
    fd_id = next(k for k, n in g.items() if n["class_type"] == "FaceDetailer")
    m2i = [k for k, n in g.items() if n["class_type"] == "MaskToImage"]
    saves = [n for n in g.values() if n["class_type"] == "SaveImage"]
    mask_saves = [n for n in saves if n["inputs"]["filename_prefix"].endswith(chain.MASK_SUFFIX)]
    check("detail graph saves the detector mask under a _mask prefix", len(mask_saves) == 1, len(mask_saves))
    check("the mask save is fed by MaskToImage reading the FaceDetailer's mask output (index 3)",
          len(m2i) == 1 and mask_saves and mask_saves[0]["inputs"]["images"][0] == m2i[0]
          and g[m2i[0]]["inputs"]["mask"] == [fd_id, 3], (m2i, mask_saves))
    check("the image save keeps the plain prefix", any(n["inputs"]["filename_prefix"] == "pre" for n in saves))
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
