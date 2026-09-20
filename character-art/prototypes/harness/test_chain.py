#!/usr/bin/env python3
"""Tests for the chain's testable decisions. Plain `python3 test_chain.py`, no pytest."""
import sys
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

    print()
    if FAILS: print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0

if __name__ == "__main__":
    sys.exit(main())
