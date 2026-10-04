#!/usr/bin/env python3
"""The game-asset stage: one generated prop to a validated glb at its category's budget, or a refusal.

stage.py SOURCE.glb --category NAME --table CONSUMER.json --rig RIG.json --out DIR
         [--lane SOURCE.glb.lane.json | --control GENERATOR] [--provisional provisional.json]

Normalises the prop by its generator's up and its category's governing axis, tries its class's rebuild
arms in order and accepts the first whose output passes the gate, then writes the LODs, the collision
mesh, the sheets and the sidecar. Exits 0 when an arm is accepted, 1 when the prop is refused, 2 when
the inputs or tools are wrong.
"""
import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import finish  # noqa: E402
import gate  # noqa: E402
import measure  # noqa: E402
import parts as P  # noqa: E402
from common import GENERATORS, export_yup, load_zup, safe_name, sha256_file, tool_paths, write_json  # noqa: E402
from normalise import normalise  # noqa: E402
from sheets import sheet  # noqa: E402

# the class's arms in order, and its collision kind (an arm's own kind where the class names one)
CLASSES = {
    "box": (["box", "generic"], {"box": "box", "generic": "hull"}),
    # a round prop the lathe cannot carry is refused, not rebuilt faceted: the generic arm made no round hit
    # on WIs 2112 and 2120's sets and accepted the jar and the keg faceted (WIs 2092, 2143)
    "round": (["lathe"], "hull"),
    "open frame": (["generic", "parts"], "part_boxes"),
    "small detailed": (["parts", "generic"], "hull"),
    "cluster": (["parts", "generic"], "part_boxes"),
    "organic": (["generic", "parts"], "hull_or_part_boxes"),
    "flat": (["planar", "generic"], "box"),
    "slab": (["box", "generic"], "box"),
}
FIELDS = ("class", "governing", "size", "budget", "texture")
VERSION = 2


def removable(path, out):
    """Whether the stage may delete `path`: only a file or folder inside its own output folder, never the
    folder itself or anything outside it."""
    root = os.path.realpath(out)
    target = os.path.realpath(path)
    return target != root and target.startswith(root + os.sep)


def remove(path, out):
    if not removable(path, out):
        raise ValueError(f"refusing to delete {path}: outside {out}")
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def fail(code, msg):
    print(f"stage: {msg}", file=sys.stderr)
    sys.exit(code)


def inputs(a):
    """The category's row, the generator and the lane record, or exit 2 naming what is wrong."""
    stem = os.path.basename(a.source)[:-4] if a.source.endswith(".glb") else None
    if not stem or not safe_name(stem):
        fail(2, f"unsafe or non-glb source name {os.path.basename(a.source)!r}")
    if not safe_name(a.category):
        fail(2, f"unsafe category name {a.category!r}")
    if not os.path.isfile(a.source):
        fail(2, f"no source {a.source}")
    table = json.load(open(a.table))
    cat = table.get("categories", {}).get(a.category)
    if cat is None:
        fail(2, f"category {a.category} is not in {a.table}")
    missing = [f for f in FIELDS if f not in cat]
    if missing:
        fail(2, f"category {a.category} lacks {', '.join(missing)}")
    if cat["class"] not in CLASSES:
        fail(2, f"unknown class {cat['class']!r} for {a.category}")
    lane = None
    if a.control:
        generator = a.control
    else:
        lane_path = a.lane or a.source + ".lane.json"
        if not os.path.isfile(lane_path):
            fail(2, f"no lane record ({lane_path}) and no control declared")
        lane = json.load(open(lane_path))
        generator = lane.get("arm")
    if generator not in GENERATORS:
        fail(2, f"unsupported generator {generator}")
    provisional = json.load(open(a.provisional)) if a.provisional else None
    return stem, cat, generator, lane, provisional


def tools():
    t = tool_paths()
    for name in ("blender", "validator"):
        if not (os.path.isfile(t[name]) and os.access(t[name], os.X_OK)):
            fail(2, f"{name} not found or not executable at {t[name]}")
    return t


def run_blender(t, cfg_path, log_path):
    """Blender's exit code, and its peak resident memory in MB (Linux reports children's in KB)."""
    with open(log_path, "w") as log:
        # Blender exits 0 on a script error unless told otherwise
        r = subprocess.run([t["blender"], "-b", "-t", t["threads"], "--python-exit-code", "1",
                            "--python", os.path.join(HERE, "blender_rebuild.py"), "--", cfg_path],
                           stdout=log, stderr=subprocess.STDOUT)
    return r.returncode, round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024)


def attempt(arm, a, ctx, t):
    """One arm: geometry, Blender's rebuild and bake, LODs, collision, measurements, gate rows."""
    d = os.path.join(a.out, "arms", arm)
    remove(d, a.out)
    os.makedirs(d)
    rec = {"arm": arm}
    mode = arm
    cfg = {"source": a.source, "matrix": ctx["norm"]["matrix"], "budget": ctx["cat"]["budget"],
           "texture": ctx["cat"]["texture"], "outdir": d, "stem": ctx["stem"], "source_parts": ctx["parts_info"]["parts"],
           "rig": ctx["rig"]}
    if arm in ("lathe", "parts"):
        builder = P.lathe_arm if arm == "lathe" else P.parts_arm
        geom, info = builder(ctx["w"], ctx["parts"], ctx["size"], ctx["cat"]["budget"])
        rec["geometry"] = info
        if geom is None:
            rec["failed"] = f"no geometry: {info.get('why', 'see geometry')}"
            return rec
        given = os.path.join(d, "given.glb")
        export_yup(geom, given)
        cfg["given"], mode = given, "given"
    if arm == "box":
        lo, hi, rec["geometry"] = P.box_bounds(ctx["w"], ctx["size"], ctx["cat"]["governing"])
        cfg["box_bounds"] = [lo.tolist(), hi.tolist()]
    cfg["mode"] = mode
    cfg_path = os.path.join(d, "blender_config.json")
    write_json(cfg_path, cfg)
    t0 = time.time()
    rc, peak = run_blender(t, cfg_path, os.path.join(d, "blender.log"))
    rec["t_blender"] = round(time.time() - t0, 1)
    rec["blender_peak_mb"] = peak
    if rc != 0 or not os.path.isfile(os.path.join(d, "blender.json")):
        rec["failed"] = f"Blender exited {rc} (peak {peak} MB resident); see {os.path.join(d, 'blender.log')}"
        return rec
    bl = json.load(open(os.path.join(d, "blender.json")))
    rec["blender"] = {k: v for k, v in bl.items() if k != "renders"}
    rec["renders"] = bl["renders"]
    lod0_path = bl["lod0"]
    rec["lods"] = finish.lods(lod0_path, d, ctx["stem"])
    lod0 = finish.load_zup(lod0_path)
    kinds = ctx["collision"]
    kind = kinds[arm] if isinstance(kinds, dict) else kinds
    coll, used = finish.collision(kind, lod0, ctx["w"], ctx["parts"])
    finish.write_collision(coll, os.path.join(d, f"{ctx['stem']}.collision.json"))
    rec["collision"] = {"kind": used, "triangles": int(len(coll.faces))}
    floating, n_pieces = measure.floating(lod0, ctx["size"])
    p95, forward, backward, buried = measure.shape_p95(ctx["w"], lod0, ctx["size"])
    tex = lod0.visual.material.baseColorTexture.size if getattr(lod0.visual, "material", None) is not None and \
        getattr(lod0.visual.material, "baseColorTexture", None) is not None else (0, 0)
    lo, hi = lod0.bounds
    ext = hi - lo
    gov = ctx["cat"]["governing"]
    m = {
        "arm": arm, "budget": ctx["cat"]["budget"], "lod0_tris": int(len(lod0.faces)),
        "lod1_tris": rec["lods"][0]["tris"], "lod2_tris": rec["lods"][1]["tris"],
        "texture": int(max(tex)), "texture_limit": ctx["cat"]["texture"], "foot": float(lo[2]),
        "governing": float(max(ext[0], ext[1]) if gov == "horizontal" else ext[2]), "governing_axis": gov,
        "size": ctx["cat"]["size"], "collision_tris": int(len(coll.faces)),
        "collision_watertight": bool(coll.is_watertight), "pieces": n_pieces,
        "source_parts": ctx["parts_info"]["parts"], "floating": floating, "shape_p95": p95,
        "colour": measure.colour_rows(bl["renders"]["even"]),
        "validator": finish.validate([lod0_path] + [l["file"] for l in rec["lods"]], t["validator"]),
    }
    rec["measurements"] = {"pieces": n_pieces, "floating": floating, "shape_p95": round(p95, 4),
                           "shape_source_to_rebuild": round(forward, 4), "shape_rebuild_to_source": round(backward, 4),
                           "buried_share": round(buried, 4), "colour": m["colour"],
                           "hull_over_volume": measure.hull_over_volume(lod0),
                           "extents": [round(float(v), 4) for v in ext]}
    rec["gate"] = gate.rows(m)
    rec["passed"] = gate.passed(rec["gate"])
    return rec


def failing(rec):
    if "failed" in rec:
        return 99
    return sum(not v["pass"] for v in rec["gate"].values())


def write_sheets(a, stem, rec):
    r = rec["renders"]
    views = ["front", "side", "back", "above"]
    even = sheet(os.path.join(a.out, f"{stem}_sheet_even.png"), views,
                 [(f"{stem} source", [r["even"][f"source_{v}"] for v in views]),
                  (f"{stem} {rec['arm']} {rec['blender']['low_tris']} tris", [r["even"][f"rebuild_{v}"] for v in views])],
                 title=f"{stem}: even light")
    rig_rows = []
    for name in [k for k in r if k != "even"]:
        rig_rows.append((f"source, {name}", [r[name]["source_front"], r[name]["source_side"]]))
        rig_rows.append((f"rebuild, {name}", [r[name]["rebuild_front"], r[name]["rebuild_side"]]))
    rig = sheet(os.path.join(a.out, f"{stem}_sheet_consumer_light.png"), ["front", "side"], rig_rows,
                title=f"{stem}: the consumer's light ({rec['arm']} arm)")
    return [even, rig]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--category", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--rig", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lane")
    ap.add_argument("--control", help="run without a lane record, naming the generator")
    ap.add_argument("--provisional")
    a = ap.parse_args(argv)
    stem, cat, generator, lane, provisional = inputs(a)
    t = tools()
    os.makedirs(a.out, exist_ok=True)
    # a refusal must leave no accepted asset behind, so an earlier run's outputs for this stem go first
    for name in (f"{stem}_lod0.glb", f"{stem}_lod1.glb", f"{stem}_lod2.glb", f"{stem}.collision.json",
                 f"{stem}.stage.json", f"{stem}_sheet_even.png", f"{stem}_sheet_consumer_light.png", "norm.json", "arms"):
        remove(os.path.join(a.out, name), a.out)
    t0 = time.time()
    source_hash = sha256_file(a.source)
    if lane is not None and lane.get("asset", {}).get("content_hash") not in (None, source_hash):
        fail(2, f"source hash {source_hash} differs from the lane record's {lane['asset']['content_hash']}")

    src = load_zup(a.source)
    norm = normalise(src, generator, cat["governing"], float(cat["size"]))
    write_json(os.path.join(a.out, "norm.json"), norm)
    src.apply_transform(np.asarray(norm["matrix"]))
    size = float(max(src.extents))
    w, parts, parts_info = P.source_parts(src, size)
    arms, collision = CLASSES[cat["class"]]
    ctx = {"stem": stem, "cat": cat, "norm": norm, "w": w, "parts": parts, "parts_info": parts_info,
           "size": size, "collision": collision, "rig": json.load(open(a.rig))}
    tried, accepted = [], None
    for arm in arms:
        rec = attempt(arm, a, ctx, t)
        tried.append(rec)
        if rec.get("passed"):
            accepted = rec
            break
    best = accepted or min(tried, key=failing)
    sheet_paths = write_sheets(a, stem, best) if "renders" in best else []
    files = {}
    if accepted:
        d = os.path.join(a.out, "arms", accepted["arm"])
        for k in (0, 1, 2):
            src_path = os.path.join(d, f"{stem}_lod{k}.glb")
            files[f"lod{k}"] = shutil.copy(src_path, os.path.join(a.out, f"{stem}_lod{k}.glb"))
        files["collision"] = shutil.copy(os.path.join(d, f"{stem}.collision.json"),
                                         os.path.join(a.out, f"{stem}.collision.json"))
    side = {
        "stage_sidecar": VERSION,
        "result": "accepted" if accepted else "refused",
        "source": {"file": os.path.basename(a.source), "content_hash": source_hash},
        "control": bool(a.control),
        "lane_record": lane,
        "provisional": provisional,
        "category": {"name": a.category, **cat},
        "normalisation": norm,
        "source_parts": parts_info,
        "class": cat["class"],
        "arms_tried": [{k: v for k, v in r.items() if k != "renders"} for r in tried],
        "accepted_arm": accepted["arm"] if accepted else None,
        "lod_triangles": ([accepted["blender"]["low_tris"]] + [l["tris"] for l in accepted["lods"]]) if accepted else None,
        "texture": accepted and accepted["blender"]["texture"],
        "collision": accepted and accepted["collision"],
        "gate": accepted["gate"] if accepted else None,
        "files": {k: os.path.basename(v) for k, v in files.items()},
        "sheets": [os.path.basename(p) for p in sheet_paths],
        "t_total": round(time.time() - t0, 1),
    }
    write_json(os.path.join(a.out, f"{stem}.stage.json"), side)
    verdict = f"accepted ({accepted['arm']})" if accepted else "refused: " + "; ".join(
        f"{r['arm']}: " + (r["failed"] if "failed" in r else ", ".join(k for k, v in r["gate"].items() if not v["pass"]))
        for r in tried)
    print(f"{stem}: {verdict} in {side['t_total']} s")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
