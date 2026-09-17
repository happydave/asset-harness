"""Spike driver (WI 1371), run inside Blender: build the v1 head at overridden parameters and render it
front-on. Imports the production generator and sets its constants; edits nothing.

  blender -b --python head_render.py -- --jobs jobs.json --outdir DIR [--full NAME]
jobs.json = [{"name": "base", "params": {"EYE_CX": 0.068, ...}}, ...]; "HS_Z"/"HS_X" set the head scale.
--full NAME also runs the generator's whole main() (checks + export) for that job, into DIR/NAME-full/.
"""
import bpy, json, math, sys
from pathlib import Path
argv = sys.argv[sys.argv.index("--") + 1:]
arg = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d
OUTDIR = Path(arg("--outdir")); OUTDIR.mkdir(parents=True, exist_ok=True)
JOBS = json.loads(Path(arg("--jobs")).read_text())
FULL = arg("--full")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # rigged-avatars/prototypes
sys.argv = sys.argv[:sys.argv.index("--")] + ["--", "--out", str(OUTDIR / f"{FULL}-full")]
import blender_v1_face_rig as g

BASE = {k: getattr(g, k) for k in ("EYE_CX", "EYE_CZ", "EYE_AX", "EYE_AZ", "MOUTH_CZ", "MOUTH_AX", "MOUTH_AZ", "BROW_CZ")}
BASE["HS_X"], BASE["HS_Z"] = g.HS[0], g.HS[2]

def apply(params):
    p = dict(BASE, **params)
    for k in ("EYE_CX", "EYE_CZ", "EYE_AX", "EYE_AZ", "MOUTH_CZ", "MOUTH_AX", "MOUTH_AZ", "BROW_CZ"):
        setattr(g, k, p[k])
    g.HS = (p["HS_X"], g.HS[1], p["HS_Z"])
    for k, v in params.items():                    # any other generator constant, e.g. EYE_BALL_R
        if k not in BASE and k.isupper() and hasattr(g, k):
            setattr(g, k, v)
    return p

def render(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {"skin": g._mat("skin", (0.92, 0.76, 0.60)), "brow": g._mat("brow", (0.26, 0.16, 0.09)),
            "lip": g._mat("lip", (0.62, 0.24, 0.24)), "cavity": g._mat("cavity", (0.05, 0.02, 0.02), rough=0.9),
            "sclera": g._mat("sclera", (0.95, 0.95, 0.95), rough=0.25), "iris": g._mat("iris", (0.09, 0.16, 0.30), rough=0.15),
            "suit": g._mat("suit", (0.30, 0.42, 0.66))}
    g.build_head(mats); g.build_body(mats)
    g.build_eyeball(g.EYE_L, g.EYE_CX, mats); g.build_eyeball(g.EYE_R, -g.EYE_CX, mats)
    scn = bpy.context.scene
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.38, 1); scn.world = world
    cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); scn.collection.objects.link(cam)
    cam.location = (0, 1.6 * g.FACE_Y, g.HZ); cam_d.lens = 110; scn.camera = cam
    cam.rotation_euler = (math.radians(90), 0, math.radians(180 if g.FACE_Y > 0 else 0))
    sun_d = bpy.data.lights.new("s", 'SUN'); sun_d.energy = 3.5; sun = bpy.data.objects.new("s", sun_d)
    scn.collection.objects.link(sun); sun.rotation_euler = (math.radians(-65 * g.FACE_Y), 0, math.radians(10))
    scn.render.resolution_x = scn.render.resolution_y = 512
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    scn.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    scn.render.filepath = str(OUTDIR / f"{name}.png")
    bpy.ops.render.render(write_still=True)

done = {}
for job in JOBS:
    try:
        done[job["name"]] = {"params": apply(job["params"]), "ok": True}
        render(job["name"])
    except BaseException as e:                     # SystemExit from a degenerate build is a finding, not a crash
        done[job["name"]] = {"params": job["params"], "ok": False, "error": f"{type(e).__name__}: {e}"}
    print("SPIKE", job["name"], done[job["name"]]["ok"], done[job["name"]].get("error", ""))
(OUTDIR / "jobs_done.json").write_text(json.dumps(done, indent=1))
if FULL:
    apply(next(j["params"] for j in JOBS if j["name"] == FULL))
    g.main()
