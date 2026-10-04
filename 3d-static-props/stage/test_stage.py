#!/usr/bin/env python3
"""Tests for the game-asset stage: plain python3 in the venv, no pytest. Exits non-zero on any failure.

Run: python3 test_stage.py [--fast]
`--fast` keeps to the cases without Blender. Without it, the end-to-end cases run the stage on small
synthetic props (Blender and glTF-Validator needed; their absence fails the run, never skips it).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import finish  # noqa: E402
import gate  # noqa: E402
import measure  # noqa: E402
import parts as P  # noqa: E402
from common import TO_Z_UP, canonical, export_yup, safe_name, tool_paths  # noqa: E402
from normalise import normalise  # noqa: E402

FAST = "--fast" in sys.argv
failures = []
TMP = tempfile.mkdtemp(prefix="stage-test-", dir=HERE)


def check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def cube(size=1.0, at=(0, 0, 0)):
    return trimesh.creation.box(extents=[size] * 3, transform=trimesh.transformations.translation_matrix(at))


def base_measurements(**over):
    m = {"budget": 300, "lod0_tris": 200, "lod1_tris": 100, "lod2_tris": 50, "texture": 512, "texture_limit": 512,
         "foot": 0.0, "governing": 1.0, "governing_axis": "horizontal", "size": 1.0, "collision_tris": 12,
         "collision_watertight": True, "pieces": 1, "source_parts": 1, "floating": [], "shape_p95": 0.01,
         "colour": {"front": 1.0}, "validator": {"gltf_validator x.glb": (True, "errors 0 warnings 0")}}
    m.update(over)
    return m


print("gate rows")
r = gate.rows(base_measurements())
check("a clean prop passes every row", gate.passed(r), json.dumps({k: v for k, v in r.items() if not v["pass"]}))
r = gate.rows(base_measurements(lod0_tris=160, budget=100, lod1_tris=80, lod2_tris=40))
check("over budget refuses on the triangle row", not r["triangles"]["pass"] and not gate.passed(r))
r = gate.rows(base_measurements(validator={"gltf_validator x.glb": (False, "errors 1 warnings 0")}))
check("a validator error refuses", not gate.passed(r) and not r["gltf_validator x.glb"]["pass"])
r = gate.rows(base_measurements(shape_p95=0.041))
check("a shape p95 over 4 % refuses", not r["shape"]["pass"])
r = gate.rows(base_measurements(colour={"front": 1.0, "side": 1.0, "back": 1.0, "above": 7.4}))
check("7.4 % from above passes (WI 2120's bookshelf, faithful)", r["colour"]["pass"], str(r["colour"]))
r = gate.rows(base_measurements(colour={"front": 1.0, "side": 1.0, "back": 1.0, "above": 8.5}))
check("8.5 % from above refuses", not r["colour"]["pass"], str(r["colour"]))
r = gate.rows(base_measurements(colour={"front": 1.0, "side": 5.5, "back": 1.0, "above": 1.0}))
check("5.5 % from the side refuses", not r["colour"]["pass"], str(r["colour"]))
r = gate.rows(base_measurements(governing=1.06))
check("a size 6 % off refuses", not r["size"]["pass"])
r = gate.rows(base_measurements(arm="box", shape_p95=0.058))
check("the box arm's shape passes at 5.8 % (WI 2091's crate reads 5.73 %)", r["shape"]["pass"], str(r["shape"]))
r = gate.rows(base_measurements(arm="generic", shape_p95=0.058))
check("another arm's shape refuses at 5.8 %", not r["shape"]["pass"], str(r["shape"]))
r = gate.rows(base_measurements(arm="box", shape_p95=0.065))
check("the box arm's shape refuses at 6.5 %", not r["shape"]["pass"], str(r["shape"]))

print("pieces against the source's parts")
src = cube()
w, parts, info = P.source_parts(src, 1.0)
check("one closed cube is one source part", info["parts"] == 1, str(info))
rebuild = trimesh.util.concatenate([cube(), cube(1.0, (1.2, 0, 0))])
_, n = measure.floating(rebuild, 1.0)
r = gate.rows(base_measurements(pieces=n, source_parts=info["parts"]))
check("two cubes against one part refuse on the pieces row", n == 2 and not r["pieces"]["pass"], f"pieces {n}")
frag = trimesh.util.concatenate([cube(1.0), cube(0.2, (0.6, 0, 0)), cube(0.2, (-0.6, 0, 0))])
_, _, finfo = P.source_parts(frag, 1.0)
check("touching fragments merge into one part", finfo["fragments"] == 3 and finfo["parts"] == 1, str(finfo))
# 0.001 apart across a cell boundary (cells of 0.01 on a size of 1): only the neighbouring-cell merge joins them
near = trimesh.util.concatenate([trimesh.creation.box(bounds=[[0.0995, 0, 0], [0.4995, 0.4, 0.4]]),
                                 trimesh.creation.box(bounds=[[0.5005, 0, 0], [0.9005, 0.4, 0.4]])])
_, _, ninfo = P.source_parts(near, 1.0)
check("parts 0.001 apart across a cell boundary merge (within the 1 % contact)", ninfo["parts"] == 1, str(ninfo))
apart = trimesh.util.concatenate([trimesh.creation.box(bounds=[[0.0, 0, 0], [0.4, 0.4, 0.4]]),
                                  trimesh.creation.box(bounds=[[0.45, 0, 0], [0.85, 0.4, 0.4]])])
_, _, ainfo = P.source_parts(apart, 1.0)
check("parts 0.05 apart stay two (beyond the 1 % contact)", ainfo["parts"] == 2, str(ainfo))

print("floating parts")
two = trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), cube(1.0, (1.3, 0, 0.5))])
_, _, tinfo = P.source_parts(two, 2.3)
check("two cubes 0.3 apart are two source parts", tinfo["parts"] == 2, str(tinfo))
raised = trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), cube(1.0, (1.3, 0, 0.8))])
fl, n = measure.floating(raised, 2.3)
r = gate.rows(base_measurements(pieces=n, source_parts=tinfo["parts"], floating=fl))
check("a cube raised 0.3 floats, and only the floating row refuses",
      len(fl) == 1 and r["pieces"]["pass"] and not r["floating"]["pass"], str(fl))
low = trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), cube(1.0, (1.3, 0, 0.505))])
fl, _ = measure.floating(low, 2.3)
check("raised 0.005 on a 2.3 prop it does not float", fl == [], str(fl))

print("scale by the governing axis")
col = trimesh.creation.box(extents=[1, 1, 3], transform=trimesh.transformations.translation_matrix([0, 0, 1.5]))
n_h = normalise(col, "trellis2", "height", 2.0)
n_w = normalise(col, "trellis2", "horizontal", 2.0)
check("a 1x1x3 column in a height category of 2 comes out 2 tall, 0.67 wide",
      np.allclose(sorted(n_h["extents_after"]), [0.6667, 0.6667, 2.0], atol=0.01), str(n_h["extents_after"]))
check("in a horizontal category of 2 it comes out 2 wide, 6 tall",
      np.allclose(sorted(n_w["extents_after"]), [2.0, 2.0, 6.0], atol=0.01), str(n_w["extents_after"]))

print("the up axis by generator")
check("TRELLIS.2's up is kept: the column stays standing though its stable pose lies it down",
      n_h["extents_after"][2] == max(n_h["extents_after"]) and n_h["stable_pose_tilt_deg"] > 45,
      f"extents {n_h['extents_after']} tilt {n_h['stable_pose_tilt_deg']}")
try:
    normalise(col, "pixal3d", "height", 2.0)
    check("an unsupported generator is refused", False)
except ValueError as e:
    check("an unsupported generator is refused", "unsupported generator pixal3d" in str(e))
chair = os.path.expanduser("~/sandbox-classic-pack/tmp/2112/src/chair.glb")
if os.path.exists(chair):
    m = trimesh.load(chair, force="mesh", process=False)
    m.apply_transform(TO_Z_UP)
    nc = normalise(m, "trellis2", "horizontal", 0.6)
    check("WI 2112's chair keeps its seat up and records the stable pose's tilt (88)",
          abs(nc["stable_pose_tilt_deg"] - 88) < 5 and nc["extents_after"][2] > 0.9, str(nc["extents_after"]))
else:
    check("WI 2112's chair source is present for the up-axis case", False, chair)

print("the lathe")
cyl = trimesh.creation.cylinder(radius=0.5, height=1.0, sections=96,
                                transform=trimesh.transformations.translation_matrix([0, 0, 0.5]))
body, linfo, _ = P.lathe(cyl, 1.0, 300)
check("a cylinder gives a lathe", body is not None, str(linfo))
if body is not None:
    check("with at least 12 sides", linfo["sides"] >= 12, str(linfo))
    check("within the budget", len(body.faces) <= 300, str(len(body.faces)))
    check("one closed piece", body.is_watertight and len(body.split(only_watertight=False)) == 1)
    check("within 1 % of the size at p95", P.p95_to(cyl, body, 1.0) <= 0.01, f"{P.p95_to(cyl, body, 1.0):.4f}")
slab = trimesh.creation.box(extents=[1.0, 0.3, 0.1])
body, linfo, _ = P.lathe(slab, 1.0, 300)
check("a flat slab has no lathe axis", body is None, str(linfo))
# an open jar: its inner wall bulges out under a narrow mouth, which no cap seen from above reaches
z_up = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], float)
jar = P._revolve(np.array([(0, 0), (0, 0.5), (0.5, 0.6), (1.0, 0.35), (1.0, 0.3), (0.5, 0.52), (0.1, 0.4),
                           (0.1, 0)], float), 96, z_up, np.zeros(3))
jar_size = float(max(jar.extents))
body, linfo, _ = P.lathe(jar, jar_size, 300)
check("an open jar's lathe follows its inner wall", body is not None and "open_top" in linfo, str(linfo))
if body is not None:
    check("and fits it within 4 % both ways", P.fit_error(jar, body, jar_size) <= P.FIT_P95,
          f"{P.fit_error(jar, body, jar_size):.4f}")
# a mug: a handle on one side moves the bounding box's centre off the body's axis
mug = trimesh.util.concatenate([
    trimesh.creation.cylinder(radius=0.4, height=1.0, sections=96,
                              transform=trimesh.transformations.translation_matrix([0, 0, 0.5])),
    trimesh.creation.box(extents=[0.12, 0.1, 0.6]).apply_translation([0.45, 0, 0.5])])
mw, mparts, _ = P.source_parts(mug, float(max(mug.extents)))
geom, ginfo = P.lathe_arm(mw, mparts, float(max(mug.extents)), 300)
check("a mug's lathe finds the body's axis, not the box's", geom is not None and ginfo.get("axis_shift", 0) > 0.03,
      str({k: ginfo.get(k) for k in ("axis_shift", "why")}))
if geom is not None:
    mp95 = measure.shape_p95(mw, geom, float(max(mug.extents)))[0]
    check("and the arm, handle and all, is within 4 %", mp95 <= 0.04, f"{mp95:.4f}")
lidded = P._revolve(np.array([(0, 0), (0, 0.5), (1.0, 0.5), (1.0, 0.45), (0.95, 0.45), (0.95, 0)], float), 96,
                    z_up, np.zeros(3))
# a simplified profile can put two points on the axis in a row, or every point there (a lathe tried on a small
# part by `fit_part`): the first revolves around the gap, the second has no surface
spool = P._revolve(np.array([(0, 0), (0.4, 0), (0.4, 0.3), (1.0, 0.3), (1.0, 0)], float), 24, z_up, np.zeros(3))
check("a profile with two axis points in a row revolves to one closed piece",
      spool is not None and spool.is_watertight, "" if spool is None else str(spool.is_watertight))
check("a profile wholly on the axis revolves to nothing",
      P._revolve(np.array([(0, 0), (0.5, 0), (1.0, 0)], float), 24, z_up, np.zeros(3)) is None)
body, linfo, _ = P.lathe(lidded, float(max(lidded.extents)), 300)
check("a barrel's lid recessed 5 % is not an open mouth", body is not None and "open_top" not in linfo, str(linfo))

print("fits checked both ways")
disc = trimesh.creation.cylinder(radius=0.5, height=0.02, sections=96)
box = P.obb_box(disc)
check("a thin disc lies within 1 % of its bounding box one way (disc to box)", P.p95_to(disc, box, 1.0) < 0.01,
      f"{P.p95_to(disc, box, 1.0):.4f}")
check("but its fit error, both ways, refuses the box at 4 %", P.fit_error(disc, box, 1.0) > P.FIT_P95,
      f"{P.fit_error(disc, box, 1.0):.4f}")

print("the box arm's box")
along = trimesh.util.concatenate([trimesh.creation.box(extents=[1.0, 0.6, 0.5]).apply_translation([0, 0, 0.25])]
                                 + [cube(0.08, (x, y, 0.3)) for x in (-0.54, 0.54) for y in (-0.15, 0.15)])
lo, hi, binfo = P.box_bounds(along, float(max(along.extents)), "horizontal")
check("a trim never shortens the governing axis past 2.5 % (latches on its ends kept)",
      hi[0] - lo[0] >= 0.975 * along.extents[0], f"{hi[0] - lo[0]:.3f} of {along.extents[0]:.3f} {binfo}")

print("the shape row's buried source points")
inner = trimesh.creation.box(extents=[0.3] * 3).apply_translation([0, 0, 0.5])  # an internal surface
src_in = trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), inner])
band = trimesh.Trimesh([[0.6, -0.2, 0.2], [0.6, 0.2, 0.2], [0.6, 0.2, 0.8], [0.6, -0.2, 0.8]], [[0, 1, 2], [0, 2, 3]])
p95, fwd, back, buried = measure.shape_p95(src_in, trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), band]), 1.0)
check("a source's internal surface inside a closed piece is left out, though an open piece is joined to it",
      fwd <= 0.04 and buried > 0, f"fwd {fwd:.4f} buried {buried:.3f}")
open_box = cube(1.0, (0, 0, 0.5))
open_box.update_faces(open_box.face_normals[:, 2] < 0.9)  # the top face removed: it encloses nothing
p95, fwd, back, buried = measure.shape_p95(src_in, open_box, 1.0)
check("inside an open piece it counts", fwd > 0.04 and buried == 0, f"fwd {fwd:.4f} buried {buried:.3f}")
ball_src = trimesh.creation.icosphere(subdivisions=3, radius=0.3).apply_translation([0, 0, 0.5])
p95, fwd, back, buried = measure.shape_p95(ball_src, cube(1.0, (0, 0, 0.5)), 1.0)
check("a box around a sphere refuses, from the rebuild back to the source", p95 > 0.04 and back > 0.04,
      f"p95 {p95:.4f} back {back:.4f}")

print("rebuilt pieces counted by the source's rule")
touching = trimesh.util.concatenate([cube(1.0, (0, 0, 0.5)), cube(0.3, (0.65, 0, 0.5))])
_, n_touch = measure.floating(touching, 1.0)
check("a body and a part touching it count as one piece", n_touch == 1, str(n_touch))

print("the parts arm's budget")
shares = P.allocate([10, 1, 1, 0.01], 40)
check("shares keep the floor of 12 and drop the smallest part to fit", shares[-1] == 0 and min(shares[:3]) >= 12 and shares.sum() <= 40, str(shares))

print("names stay inside the output folder")
check("`../x` is unsafe", not safe_name("../x"))
check("`a/b` is unsafe", not safe_name("a/b"))
check("`bench` is safe", safe_name("bench"))

print("the stage deletes only inside its output folder")
import stage as STAGE  # noqa: E402
outdir = os.path.join(TMP, "owned")
os.makedirs(outdir, exist_ok=True)
check("a file inside the output folder is removable", STAGE.removable(os.path.join(outdir, "x_lod0.glb"), outdir))
check("the output folder itself is not", not STAGE.removable(outdir, outdir))
check("`../x` beside it is not", not STAGE.removable(os.path.join(outdir, "..", "x"), outdir))
check("an absolute path elsewhere is not", not STAGE.removable("/etc/passwd", outdir))
check("a sibling sharing its name's prefix is not", not STAGE.removable(outdir + "-other/f", outdir))

print("a missing tool")
toolsrc = os.path.join(TMP, "tool.glb")
export_yup(cube(), toolsrc)
r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), toolsrc, "--category", "barrel",
                    "--table", os.path.join(HERE, "consumers", "sandbox-classic-pack.json"), "--rig",
                    os.path.join(HERE, "rigs", "sandbox-classic-pack.json"), "--out", os.path.join(TMP, "tool_out"), "--control", "trellis2"],
                   capture_output=True, text=True, env={**os.environ, "STAGE_BLENDER": "/nonexistent/blender"})
check("a missing Blender exits 2 naming it", r.returncode == 2 and "blender not found" in r.stderr, r.stderr[-200:])

print("the batch is pinned to its slice")
lst = os.path.join(TMP, "list.json")
json.dump({"table": "t", "rig": "r", "items": []}, open(lst, "w"))
have = sorted(os.sched_getaffinity(0))
other = "0" if 0 not in have else str(max(have) + 1)
r = subprocess.run([sys.executable, os.path.join(HERE, "batch.py"), lst, os.path.join(TMP, "b_out"), "--cpus", other],
                   capture_output=True, text=True)
check("a batch whose affinity is not the slice it was given refuses (exit 2)",
      r.returncode == 2 and "affinity" in r.stderr, r.stderr[-200:])
spec = ",".join(str(c) for c in have)
r = subprocess.run([sys.executable, os.path.join(HERE, "batch.py"), lst, os.path.join(TMP, "b_out"), "--cpus", spec],
                   capture_output=True, text=True)
check("on its own slice the same batch runs", r.returncode == 0, r.stderr[-200:])

print("the consumer table")
table = json.load(open(os.path.join(HERE, "consumers", "sandbox-classic-pack.json")))
manifest = json.load(open(os.path.join(HERE, "..", "prototypes", "shape_set", "zone_pool_manifest.json")))
need = [i["name"] for i in manifest["items"]] + ["stump", "bench", "crate"]
missing = [n for n in need if n not in table["categories"]]
incomplete = [n for n, c in table["categories"].items() if any(f not in c for f in ("class", "governing", "size", "budget", "texture"))]
check("every test-set category is in the table with its five fields", not missing and not incomplete,
      f"missing {missing} incomplete {incomplete}")

print("the validator")
tools = tool_paths()
good = os.path.join(TMP, "good.glb")
export_yup(cube(), good)
rows = finish.validate([good], tools["validator"])
check("a clean glb passes the validator", all(ok for ok, _ in rows.values()), str(rows))
bad = os.path.join(TMP, "bad.glb")
data = bytearray(open(good, "rb").read())
jlen = int.from_bytes(data[12:16], "little")
doc = json.loads(data[20:20 + jlen])
doc["accessors"][0]["count"] += 1000   # an accessor reading past its buffer view
text = json.dumps(doc).encode()
text += b" " * (-len(text) % 4)
out = data[:12] + len(text).to_bytes(4, "little") + data[16:20] + text + data[20 + jlen:]
out[8:12] = len(out).to_bytes(4, "little")
open(bad, "wb").write(out)
rows = finish.validate([bad], tools["validator"])
check("a glb with a broken accessor fails the validator row", not any(ok for ok, _ in rows.values()), str(rows))
rows = finish.validate([good], os.path.join(TMP, "no-such-validator"))
check("a validator that cannot run fails the row", not any(ok for ok, _ in rows.values()), str(rows))

if not FAST:
    print("end to end (Blender)")
    rig = os.path.join(HERE, "rigs", "sandbox-classic-pack.json")
    tab = os.path.join(TMP, "table.json")
    json.dump({"categories": {
        "can": {"class": "round", "governing": "horizontal", "size": 1.0, "budget": 300, "texture": 256},
        "ball": {"class": "box", "governing": "horizontal", "size": 1.0, "budget": 300, "texture": 256},
    }}, open(tab, "w"))

    def stage(src, category, out, *extra):
        r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), src, "--category", category, "--table", tab,
                            "--rig", rig, "--out", out, *extra], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    can = os.path.join(TMP, "can.glb")
    export_yup(trimesh.creation.cylinder(radius=0.5, height=1.0, sections=64,
                                         transform=trimesh.transformations.translation_matrix([0, 0, 0.5])), can)
    lane = {"asset": {"content_hash": None}, "arm": "trellis2", "license_record": {"status": "conditional", "text": "test"}}
    json.dump(lane, open(can + ".lane.json", "w"))
    prov = {"provisional": {"style": "unanchored", "licence": "conditional"}, "ships": False}
    prov_path = os.path.join(TMP, "provisional.json")
    json.dump(prov, open(prov_path, "w"))
    out = os.path.join(TMP, "can_out")
    rc, txt = stage(can, "can", out, "--provisional", prov_path)
    side = json.load(open(os.path.join(out, "can.stage.json"))) if os.path.exists(os.path.join(out, "can.stage.json")) else {}
    check("a cylinder in the round class is accepted by the lathe arm", rc == 0 and side.get("accepted_arm") == "lathe", txt[-400:])
    if side:
        lat = side["arms_tried"][0].get("geometry", {})
        check("its lathe has at least 12 sides", lat.get("sides", 0) >= 12, str(lat))
        check("the lane record is carried unchanged", canonical(side["lane_record"]) == canonical(lane))
        check("the provisional record is carried unchanged", canonical(side["provisional"]) == canonical(prov))
        check("its LODs, collision and sidecar are written", all(os.path.exists(os.path.join(out, f)) for f in
              ("can_lod0.glb", "can_lod1.glb", "can_lod2.glb", "can.collision.json")))

    # a round category's source the lathe cannot carry (no axis with circular cross-sections) is refused,
    # where the generic arm would have accepted it faceted
    plank = os.path.join(TMP, "plank.glb")
    export_yup(trimesh.creation.box(extents=[1.0, 0.3, 0.1]).apply_translation([0, 0, 0.05]), plank)
    json.dump(lane, open(plank + ".lane.json", "w"))
    out = os.path.join(TMP, "plank_out")
    rc, txt = stage(plank, "can", out)
    f = os.path.join(out, "plank.stage.json")
    side = json.load(open(f)) if os.path.exists(f) else {}
    check("a round prop the lathe cannot carry is refused, the lathe its only arm",
          rc == 1 and [a["arm"] for a in side.get("arms_tried", [])] == ["lathe"], f"exit {rc} {txt[-200:]}")

    # a sphere's lathe is 196 triangles at a budget of 200 and 256 at 300: the budget binds
    pot = os.path.join(TMP, "pot.glb")
    export_yup(trimesh.creation.icosphere(subdivisions=4, radius=0.5).apply_translation([0, 0, 0.5]), pot)
    json.dump(lane, open(pot + ".lane.json", "w"))
    json.dump({"categories": {"pot": {"class": "round", "governing": "horizontal", "size": 1.0, "budget": 200, "texture": 256}}},
              open(os.path.join(TMP, "pot.json"), "w"))
    out = os.path.join(TMP, "pot_out")
    r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), pot, "--category", "pot", "--table",
                        os.path.join(TMP, "pot.json"), "--rig", rig, "--out", out], capture_output=True, text=True)
    side = json.load(open(os.path.join(out, "pot.stage.json"))) if os.path.exists(os.path.join(out, "pot.stage.json")) else {}
    check("the Python-built arms build to the table's budget: a sphere at 200 is accepted by the lathe at 200 or fewer",
          r.returncode == 0 and side.get("accepted_arm") == "lathe" and (side.get("lod_triangles") or [999])[0] <= 200,
          f"{side.get('accepted_arm')} {side.get('lod_triangles')} {(r.stdout + r.stderr)[-200:]}")

    ball = os.path.join(TMP, "ball.glb")
    export_yup(trimesh.creation.icosphere(subdivisions=4, radius=0.5).apply_translation([0, 0, 0.5]), ball)
    json.dump(lane, open(ball + ".lane.json", "w"))
    out = os.path.join(TMP, "ball_out")
    rc, txt = stage(ball, "ball", out)
    side = json.load(open(os.path.join(out, "ball.stage.json"))) if os.path.exists(os.path.join(out, "ball.stage.json")) else {}
    arms = [a["arm"] for a in side.get("arms_tried", [])]
    first = side.get("arms_tried", [{}])[0]
    check("a sphere in the box class falls back from box to generic, both recorded",
          rc == 0 and arms == ["box", "generic"] and side.get("accepted_arm") == "generic"
          and not first.get("gate", {}).get("shape", {}).get("pass", True), f"{arms} {txt[-300:]}")

    # a closed box with latches standing 0.08 off two faces: a box on its extremes stands off the body by
    # them (6.7 % of the size), one fitted to the body does not. A box with a domed lid is no box.
    json.dump({"categories": {"chest": {"class": "box", "governing": "horizontal", "size": 1.2, "budget": 300, "texture": 256}}},
              open(os.path.join(TMP, "chest.json"), "w"))
    latches = [cube(0.08, (x, y, 0.4)) for x in (-0.3, 0.3) for y in (-0.44, 0.44)]
    for name, mesh in (("latched", trimesh.util.concatenate(
            [trimesh.creation.box(extents=[1.2, 0.8, 0.7]).apply_translation([0, 0, 0.35])] + latches)),
            ("domed", trimesh.util.concatenate([
                trimesh.creation.box(extents=[1.2, 0.8, 0.5]).apply_translation([0, 0, 0.25]),
                trimesh.creation.cylinder(radius=0.4, height=1.2, sections=48,
                                          transform=trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
                .apply_translation([0, 0, 0.5])]))):
        src = os.path.join(TMP, f"{name}.glb")
        export_yup(mesh, src)
        json.dump(lane, open(src + ".lane.json", "w"))
        out = os.path.join(TMP, f"{name}_out")
        r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), src, "--category", "chest", "--table",
                            os.path.join(TMP, "chest.json"), "--rig", rig, "--out", out], capture_output=True, text=True)
        f = os.path.join(out, f"{name}.stage.json")
        side = json.load(open(f)) if os.path.exists(f) else {}
        box = (side.get("arms_tried") or [{}])[0]
        if name == "latched":
            check("a closed box with latches is accepted by the box arm", side.get("accepted_arm") == "box",
                  f"{box.get('geometry')} {box.get('measurements', {}).get('shape_p95')} {(r.stdout + r.stderr)[-200:]}")
        else:
            check("a box with a domed lid is refused by the box arm on shape",
                  box.get("arm") == "box" and not box.get("gate", {}).get("shape", {}).get("pass", True),
                  f"{box.get('measurements', {}).get('shape_p95')} {(r.stdout + r.stderr)[-200:]}")

    speck = os.path.join(TMP, "speck.glb")
    export_yup(trimesh.util.concatenate([trimesh.creation.icosphere(subdivisions=3, radius=0.5).apply_translation([0, 0, 0.5]),
                                         cube(0.04, (0.0, 0, 1.2))]), speck)
    json.dump(lane, open(speck + ".lane.json", "w"))
    json.dump({"categories": {"lump": {"class": "organic", "governing": "horizontal", "size": 1.0, "budget": 300, "texture": 256}}},
              open(os.path.join(TMP, "lump.json"), "w"))
    out = os.path.join(TMP, "speck_out")
    r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), speck, "--category", "lump", "--table",
                        os.path.join(TMP, "lump.json"), "--rig", rig, "--out", out], capture_output=True, text=True)
    side = json.load(open(os.path.join(out, "speck.stage.json"))) if os.path.exists(os.path.join(out, "speck.stage.json")) else {}
    gen = (side.get("arms_tried") or [{}])[0]
    check("a speck under 1 % of the area is debris: the generic arm drops it and is accepted",
          r.returncode == 0 and side.get("accepted_arm") == "generic" and gen.get("blender", {}).get("debris_islands_dropped", 0) >= 1,
          (r.stdout + r.stderr)[-300:])

    side = json.load(open(os.path.join(TMP, "ball_out", "ball.stage.json")))
    check("each arm records Blender's peak memory", all(t.get("blender_peak_mb", 0) > 0 for t in side["arms_tried"]),
          str([t.get("blender_peak_mb") for t in side["arms_tried"]]))
    stale = os.path.join(TMP, "ball_out")
    json.dump({"categories": {"ball": {"class": "box", "governing": "horizontal", "size": 1.0, "budget": 8, "texture": 256}}},
              open(os.path.join(TMP, "tiny.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), ball, "--category", "ball", "--table",
                        os.path.join(TMP, "tiny.json"), "--rig", rig, "--out", stale], capture_output=True, text=True)
    check("a refusal into a folder an earlier run accepted into leaves no accepted glb",
          r.returncode == 1 and os.path.exists(os.path.join(stale, "ball.stage.json"))
          and not os.path.exists(os.path.join(stale, "ball_lod0.glb")), (r.stdout + r.stderr)[-300:])

    json.dump({"categories": {"lump": {"class": "organic", "governing": "horizontal", "size": 1.0, "budget": 120, "texture": 256}}},
              open(os.path.join(TMP, "lump120.json"), "w"))
    out = os.path.join(TMP, "lump120_out")
    r = subprocess.run([sys.executable, os.path.join(HERE, "stage.py"), ball, "--category", "lump", "--table",
                        os.path.join(TMP, "lump120.json"), "--rig", rig, "--out", out], capture_output=True, text=True)
    side = json.load(open(os.path.join(out, "ball.stage.json"))) if os.path.exists(os.path.join(out, "ball.stage.json")) else {}
    check("Blender's arms build to the table's budget: a ball at 120 is accepted by the generic arm at 120 or fewer",
          r.returncode == 0 and side.get("accepted_arm") == "generic" and (side.get("lod_triangles") or [999])[0] <= 120,
          f"{side.get('accepted_arm')} {side.get('lod_triangles')} {(r.stdout + r.stderr)[-200:]}")

    nolane = os.path.join(TMP, "nolane.glb")
    shutil.copy(ball, nolane)
    out = os.path.join(TMP, "nolane_out")
    rc, txt = stage(nolane, "ball", out)
    check("a source without a lane record is refused (exit 2)", rc == 2 and "no lane record" in txt, txt[-200:])
    rc, txt = stage(nolane, "ball", out, "--control", "trellis2")
    side = json.load(open(os.path.join(out, "nolane.stage.json"))) if os.path.exists(os.path.join(out, "nolane.stage.json")) else {}
    check("declared a control naming trellis2, it runs and says control", rc == 0 and side.get("control") is True, txt[-200:])
    out = os.path.join(TMP, "unsafe_out")
    rc, txt = stage(ball, "../x", out)
    check("a category `../x` is refused before any write", rc == 2 and not os.path.exists(out), txt[-200:])

shutil.rmtree(TMP, ignore_errors=True)
print(f"{len(failures)} failed" + (f": {failures}" if failures else ""))
sys.exit(1 if failures else 0)
