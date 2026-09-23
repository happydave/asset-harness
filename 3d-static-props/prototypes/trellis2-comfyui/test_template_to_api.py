#!/usr/bin/env python3
"""Tests for template_to_api.py, plain `python3 test_template_to_api.py`, host python3, no pytest.

Fixtures under fixtures/template_to_api/<ComfyUI tag>/: the shipped template, the server's
/object_info trimmed to the template's node types, and the API graphs a run actually used, which
the conversion must reproduce exactly.
"""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import template_to_api as T  # noqa: E402

FIX = HERE / "fixtures" / "template_to_api"
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def load(tag, name):
    return json.loads((FIX / tag / name).read_text())


def refused(template, oi, **kw):
    try:
        T.convert(template, oi, kw.get("image", "x.png"), kw.get("prefix", "p"), kw.get("overrides", {}),
                  kw.get("defaults", frozenset()))
    except T.ConversionError as exc:
        return str(exc)
    return None


def main():
    print("template_to_api")
    tpl, oi = load("v0.34.6", "template.json"), load("v0.34.6", "object_info.json")

    # the graphs WI 1761 ran, reproduced
    g = T.convert(tpl, oi, "prop_crate.png", "3d/wi1761_trellis2", {316: "true"})  # overrides arrive as --set strings
    check("v0.34.6 TRELLIS.2 arm equals the graph WI 1761 ran", T.diff(g, load("v0.34.6", "trellis2_arm.json")) == [],
          T.diff(g, load("v0.34.6", "trellis2_arm.json"))[:5])
    g = T.convert(tpl, oi, "prop_crate.png", "3d/wi1761_pixal3d", {})
    check("v0.34.6 Pixal3D arm (the default) equals the graph WI 1761 ran",
          T.diff(g, load("v0.34.6", "pixal3d_arm.json")) == [], T.diff(g, load("v0.34.6", "pixal3d_arm.json"))[:5])

    fresh = load("v0.34.6", "template.json")      # its switch reads false, so an override would show
    before = json.dumps(fresh, sort_keys=True)
    T.convert(fresh, oi, "prop_crate.png", "p", {316: "true"})
    check("convert leaves the caller's template unchanged", json.dumps(fresh, sort_keys=True) == before)

    # refusals, each naming the node
    t2 = copy.deepcopy(tpl)
    victim = next(n for n in t2["nodes"] if n["type"] == "RemeshMesh")
    victim["widgets_values"] = victim["widgets_values"][:-1]
    msg = refused(t2, oi)
    check("a missing widget value is refused, naming the node", msg is not None and str(victim["id"]) in msg, msg)
    oi2 = {k: v for k, v in oi.items() if k != "UnwrapMesh"}
    msg = refused(tpl, oi2)
    check("a node type the server lacks is refused", msg is not None and "UnwrapMesh" in msg, msg)
    t3 = copy.deepcopy(tpl)
    next(n for n in t3["nodes"] if n["type"] == "DecimateMesh")["mode"] = 4
    msg = refused(t3, oi)
    check("a bypassed node is refused", msg is not None and "mode 4" in msg, msg)

    # v0.37.2: the same single-image template against the newer server
    oi37 = load("v0.37.2", "object_info.json")
    msg = refused(tpl, oi37)
    check("a widget the newer server added stops the conversion, naming --default",
          msg is not None and "--default MoGeInference.refine_steps" in msg, msg)
    filled = []
    g = T.convert(tpl, oi37, "prop_crate.png", "3d/wi1761_pixal3d", {}, frozenset({"MoGeInference.refine_steps"}), filled)
    check("with --default it takes the schema default and reports it",
          g["56"]["inputs"].get("refine_steps") == 3 and len(filled) == 1 and "refine_steps = 3" in filled[0], filled)
    check("and otherwise equals the graph WI 1761 ran",
          [d for d in T.diff(g, load("v0.34.6", "pixal3d_arm.json")) if "refine_steps" not in d] == [])

    # v0.37.2 multi-view template
    mv = load("v0.37.2", "multi_views_template.json")
    try:
        g = T.convert(mv, oi37, "sheet.png", "3d/mv", {}, frozenset({"MoGeInference.refine_steps"}))
    except T.ConversionError as exc:  # a SystemExit: caught, or it would end the suite
        g = {"refused": str(exc)}
    check("the multi-view template converts", "refused" not in g, g.get("refused"))
    crops = {n["id"]: n["widgets_values"][0] for n in mv["nodes"] if n["type"] == "ImageCropV2"}
    check("each crop region is the template's own dict", crops and all(
        g.get(str(k), {}).get("inputs", {}).get("crop_region") == v for k, v in crops.items()), crops)
    views = sorted(v["inputs"]["filename_prefix"] for v in g.values() if isinstance(v, dict) and v.get("class_type") == "SaveImageAdvanced")
    check("the view crops keep their labels under the prefix",
          views == ["3d/mv_back_view", "3d/mv_front_view", "3d/mv_left_view", "3d/mv_right_view"], views)
    check("a default-named output takes the prefix itself",
          [v["inputs"]["filename_prefix"] for v in g.values() if isinstance(v, dict) and v.get("class_type") == "Save3DAdvanced"] == ["3d/mv"])
    mv2 = copy.deepcopy(mv)
    next(n for n in mv2["nodes"] if n["type"] == "ImageCropV2")["widgets_values"][1] = "x"
    msg = refused(mv2, oi37, defaults=frozenset({"MoGeInference.refine_steps"}))
    check("unexpected crop component values are refused", msg is not None and "crop component" in msg, msg)

    print(f"{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all ok'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
