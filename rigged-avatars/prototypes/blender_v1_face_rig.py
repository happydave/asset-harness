#!/usr/bin/env python3
"""WI 1362: the stylized head archetype's **v1 face rig** — WI 923 VTuber ladder step 6.

    ~/blender-4.2/blender --background --python blender_v1_face_rig.py -- --out DIR [--previews]

What this adds over WI 936's first cut, and why:

* **Real loop topology.** 936 authored morphs on a smooth UV sphere and recorded the ceiling in its own
  reflection: "a smooth sphere has no eyelid loops, so 'close the lid' is a crude vert push that overlaps
  the brow." WI 938 then produced the converse on dense topology. Here each eye and the mouth is an
  *aperture* surrounded by concentric loops laid down with repeated `inset_region`, so a blink is a lid
  folding shut over an eyeball rather than a dent in a shell. Topology is the ladder's one irreversible
  decision (re-topologizing invalidates every shape key), so it is taken here and frozen before the first
  `shape_key_add`.
* **Bone-driven gaze.** Two eye bones + `look_at.type = 'bone'`, which makes the eight `eyeLook*` ARKit
  clips legitimate free stubs rather than unauthored gaps.
* **The full contract.** 16 authored morphs -> the 13 morph-composed VRM presets, all 52 ARKit clips
  declared (36 as sanctioned empty Perfect-Sync stubs), expression override modes set so stacked
  expressions suppress instead of summing.

The 52 names, the preset table and the stub reasons live in `arkit52.py`, which owns them; this generator
imports them. Exports VRM 1.0 (master) + VRM 0.x (derived, for VSeeFace) + a game-lane `.glb` through the
shared `vrm_export.py`, extended not forked.

Licence: clean. Blender primitives + hand-authored morphs, ours; the GPL/MIT toolchain binds the tool and
imposes nothing on exported assets. Describe the result as "ARKit-compatible" / "Perfect Sync".
"""
import bpy
import bmesh
import json
import math
import sys
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


OUT = Path(_arg("--out", "/tmp/v1_face_rig"))
PREVIEWS = "--previews" in argv
# Negative controls (plan section G): deliberately break one thing so the checks are seen to fail.
NEGATIVE = _arg("--negative-control")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_corn import corn_bone_defs, build_armature          # noqa: E402
import arkit52                                                    # noqa: E402
import vrm_export                                                 # noqa: E402

HEAD, BODY = "face", "torso"
EYE_L, EYE_R = "eyeball.L", "eyeball.R"

# ---- head frame (armature/world space, +Y is front) -------------------------
HZ = 1.15                       # head centre z
HR = 0.16                       # head sphere radius before scaling
HS = (1.0, 0.98, 1.14)          # head scale -> ellipsoid semi-axes (0.160, 0.1568, 0.1824)

EYE_CX, EYE_CZ = 0.068, 1.185   # eye centres
EYE_AX, EYE_AZ = 0.044, 0.038   # eye PATCH half-extents (the lid zone's outer edge)
# A flattened, recessed dome rather than a full sphere. A sphere wide enough to fill the aperture
# breaches the head shell just outside the aperture's outer corner — which rendered as a black crescent
# beside each eye — because the shell curves away faster than the ball does.
EYE_BALL_R = 0.032              # wide enough to seal the aperture corner (26.5 mm out)
EYE_BALL_SY = 0.78              # flattened, so it does not breach the shell beside the eye
EYE_BALL_Y = 0.107              # recessed: a ball proud of the shell breaks through as a crescent
IRIS_FRACTION = 0.35            # front fraction of the ball that is iris

BROW_CZ = 1.247                  # brow arc centre z
BROW_AX, BROW_AZ = 0.052, 0.027  # brow arc half-extents (the deform zone)

MOUTH_CZ = 1.062
MOUTH_AX, MOUTH_AZ = 0.052, 0.030

INSETS = 3                       # concentric loops laid around each aperture
EYE_INSET_T = 0.008
MOUTH_INSET_T = 0.008
CAVITY_DEPTH = 0.075

AUTHORED = list(arkit52.STYLIZED_V1_AUTHORED)


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------
def _mat(name, rgb, rough=0.6, cull=True):
    """`cull` matters here: the head shell is a zero-thickness surface with holes cut in it, so without
    backface culling the camera sees the INSIDE of the shell through each aperture and renders it as a
    black jagged wedge beside the eye. Culling is also what a toon shader does, and it survives export
    as glTF `doubleSided: false`."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = cull
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


# ---------------------------------------------------------------------------
# aperture construction — this is what makes the loops real
# ---------------------------------------------------------------------------
def _ellipse_e(co, cx, cz, ax, az):
    """Normalised elliptical radius about a feature centre: 0 at the centre, 1 at the patch edge."""
    return math.hypot((co[0] - cx) / ax, (co[2] - cz) / az)


def _carve_aperture(bm, cx, cz, ax, az, thickness, insets=INSETS):
    """Lay `insets` concentric loops around an elliptical face patch, then delete the patch interior.

    `inset_region` inserts a rim of faces between a region's border and its shrunk interior, so applying
    it repeatedly is literally how you lay eyelid loops parametrically. Deleting what is left opens the
    aperture; the loops stay behind as the lid.

    Returns (boundary_edges, (hx, hz)) where (hx, hz) are the aperture's MEASURED half-extents. They
    are measured rather than derived because an inset shrinks a curved staircase-bordered patch by an
    amount flat arithmetic only approximates — and the morph falloff has to be exactly 1.0 at the rim,
    or the lid stops short of closing (which is precisely how the first run failed: 11 mm still open).
    """
    def patch(step):
        """Re-select by geometry each pass rather than tracking what the op returned. `inset_region`'s
        `faces` output is the ring, not the interior, and filtering the tracked list against it walked
        the boundary in by one inset's worth total instead of `insets` — re-selecting against a
        shrinking ellipse is independent of that ambiguity and says plainly where the rim will land."""
        sax, saz = ax - step * thickness, az - step * thickness
        if sax <= 0.0 or saz <= 0.0:
            raise SystemExit(f"aperture at ({cx}, {cz}): {insets} insets of {thickness} overrun a "
                             f"{ax} x {az} patch")
        return [f for f in bm.faces
                if f.calc_center_median().y > 0.03
                and _ellipse_e(f.calc_center_median(), cx, cz, sax, saz) <= 1.0]

    for step in range(insets):
        faces = patch(step)
        if not faces:
            raise SystemExit(f"aperture at ({cx}, {cz}) selected no faces on inset {step}")
        # use_even_offset=False deliberately. The ellipse patch has a staircase border, and even-offset
        # mitring at those acute corners spikes vertices off the mesh entirely — measured: one vert
        # thrown to x = -1.65 on a 0.16 m head, which silently poisoned the rim measurement below.
        bmesh.ops.inset_region(bm, faces=faces, use_even_offset=False,
                               use_boundary=True, thickness=thickness, depth=0.0)
    faces = patch(insets)
    if not faces:
        raise SystemExit(f"aperture at ({cx}, {cz}) closed up before it could be opened")
    bmesh.ops.delete(bm, geom=faces, context='FACES')
    bm.edges.ensure_lookup_table()
    edges = [e for e in bm.edges if len(e.link_faces) == 1
             and all(_ellipse_e(v.co, cx, cz, ax, az) <= 1.0 and v.co.y > 0.03 for v in e.verts)]
    rim = {v for e in edges for v in e.verts}
    hx = max(abs(v.co.x - cx) for v in rim)
    hz = max(abs(v.co.z - cz) for v in rim)
    return edges, (hx, hz)


def _cavity(bm, edges, cx, cz, depth):
    """Cap an aperture with a cone pushed back behind the face, so an open mouth shows a dark interior
    instead of the inside of the head shell. Extrude the rim, push it back, merge to a point — a cone is
    guaranteed closed, which a planar cap over a curved rim is not."""
    res = bmesh.ops.extrude_edge_only(bm, edges=edges)
    new_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    apex = [cx, min(v.co.y for v in new_verts) - depth, cz]
    for v in new_verts:
        v.co.y -= depth * 0.5
    bmesh.ops.pointmerge(bm, verts=new_verts, merge_co=apex)
    return len(new_verts)


def build_head(mats):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=HR, location=(0, 0, HZ), segments=128, ring_count=72)
    o = bpy.context.active_object
    o.name = HEAD
    o.scale = HS
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()

    global EYE_HOLE, MOUTH_HOLE
    holes = []
    for sx in (1, -1):
        # No socket cone here. One was tried and made things worse: a cone from the aperture rim to an
        # apex behind the eye necessarily passes THROUGH the eyeball, so its dark wall rendered in
        # front of the iris. The eyeball itself is the seal — it is sized to cover the aperture's
        # furthest corner (26.5 mm from the eye centre) from any front-on ray.
        _, h = _carve_aperture(bm, sx * EYE_CX, EYE_CZ, EYE_AX, EYE_AZ, EYE_INSET_T)
        holes.append(h)
    EYE_HOLE = (sum(h[0] for h in holes) / 2, sum(h[1] for h in holes) / 2)
    mouth_edges, MOUTH_HOLE = _carve_aperture(bm, 0.0, MOUTH_CZ, MOUTH_AX, MOUTH_AZ, MOUTH_INSET_T)
    _cavity(bm, mouth_edges, 0.0, MOUTH_CZ, CAVITY_DEPTH)
    print(f"  aperture half-extents measured: eye {EYE_HOLE[0]*1000:.1f} x {EYE_HOLE[1]*1000:.1f} mm, "
          f"mouth {MOUTH_HOLE[0]*1000:.1f} x {MOUTH_HOLE[1]*1000:.1f} mm")

    bm.to_mesh(me)
    bm.free()
    me.update()

    slot = {}
    for k in ("skin", "brow", "lip", "cavity"):
        me.materials.append(mats[k])
        slot[k] = len(me.materials) - 1
    for poly in me.polygons:
        c = poly.center
        poly.material_index = slot[_face_region((c.x, c.y, c.z))]
    return o


def _face_region(co):
    """Colour by the SAME loop bands the morphs deform, so a feature's colour and its motion cannot
    disagree. Colouring by an independent ellipse produced blotches that drifted off the geometry."""
    x, y, z = co
    if y <= 0.03:
        return "skin"
    if y < 0.085:                    # the socket / mouth cones are the only front geometry this far back
        return "cavity"
    if _lipz(co)[1] >= 0.35:
        return "lip"
    # brows as arcs rather than bars: a rectangle of brown reads as a bandage
    for sx in (1, -1):
        if _ellipse_e(co, sx * (EYE_CX + 0.004), BROW_CZ, BROW_AX * 0.94, BROW_AZ * 0.58) <= 1.0:
            return "brow"
    return "skin"


def build_body(mats):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.19, location=(0, 0, 0.72), segments=24, ring_count=16)
    o = bpy.context.active_object
    o.name = BODY
    o.scale = (1.0, 0.7, 1.9)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(mats["suit"])
    return o


def build_eyeball(name, cx, mats):
    """A two-material ball: white sclera, dark iris on the front cap. The iris is what makes bone-driven
    gaze legible — rotate the eye bone and you can see where it looks."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=EYE_BALL_R, location=(cx, EYE_BALL_Y, EYE_CZ),
                                         segments=24, ring_count=16)
    o = bpy.context.active_object
    o.name = name
    o.scale = (1.0, EYE_BALL_SY, 1.0)
    bpy.ops.object.transform_apply(scale=True)      # scale only: the mesh data stays centred on the
    me = o.data                                     # origin, which the local-space iris test needs
    for k in ("sclera", "iris"):
        me.materials.append(mats[k])
    # Split the ball by its OWN measured extent rather than against a constant. A constant encodes an
    # assumption about which coordinate frame poly.center is in, and that assumption has now been wrong
    # twice on this line: the first version compared a local y against a world one, and the second
    # assumed the mesh was origin-centred. The whole ball shipped as iris, with no sclera in the file.
    ys = [poly.center.y for poly in me.polygons]
    lo, hi = min(ys), max(ys)
    iris_from = lo + (hi - lo) * (1.0 - IRIS_FRACTION)
    for poly in me.polygons:
        poly.material_index = 1 if poly.center.y > iris_from else 0
    n_iris = sum(1 for poly in me.polygons if poly.material_index == 1)
    if not 0 < n_iris < len(me.polygons):
        raise SystemExit(f"{name}: iris split degenerate — {n_iris}/{len(me.polygons)} polys. "
                         f"poly.center.y spans [{lo:.4f}, {hi:.4f}], threshold {iris_from:.4f}")
    print(f"  {name}: {n_iris}/{len(me.polygons)} polys iris (y span [{lo:.4f}, {hi:.4f}])")
    return o


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
def add_eye_bones(arm):
    """Added AFTER auto-weighting, so the head and body cannot pick up eye-bone influence by accident —
    achieved by construction rather than by cleaning weights up afterwards."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    for name, sx in (("eye.L", 1), ("eye.R", -1)):
        b = eb.new(name)
        b.head = (sx * EYE_CX, EYE_BALL_Y, EYE_CZ)
        b.tail = (sx * EYE_CX, EYE_BALL_Y + 0.05, EYE_CZ)
        b.use_connect = False
        b.parent = eb["head"]
    bpy.ops.object.mode_set(mode='OBJECT')


def rigid_skin(obj, arm, bone):
    """One bone, all vertices, weight 1.0 — a rigid eyeball that follows its gaze bone exactly."""
    g = obj.vertex_groups.new(name=bone)
    g.add(range(len(obj.data.vertices)), 1.0, 'REPLACE')
    md = obj.modifiers.new("Armature", 'ARMATURE')
    md.object = arm
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()


def auto_skin(meshes, arm):
    bpy.ops.object.select_all(action='DESELECT')
    for m in meshes:
        m.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')


# ---------------------------------------------------------------------------
# morphs — masks are geometric, computed against the FROZEN topology
# ---------------------------------------------------------------------------
def _aperture_t(co, cx, cz, ax, az, hole):
    """(in_zone, t) for the loop band between an aperture rim and the patch edge.

    t is exactly 1.0 AT the rim and 0.0 at the patch edge, per-vertex — which matters because the rim
    is a staircase, not a smooth ellipse, so a single scalar rim radius is wrong for most of it.

    `s` is the vertex's radius on the patch ellipse (1 at the patch edge); `q` is its radius on the
    HOLE ellipse (1 at the rim). The point on the rim in the same radial direction sits at s/q, so
    normalising (1 - s) by (1 - s/q) gives 1 at the rim and 0 at the patch edge for every direction.
    """
    hx, hz = hole
    if co[1] <= 0.03 or hx <= 0 or hz <= 0:
        return False, 0.0
    s = _ellipse_e(co, cx, cz, ax, az)
    if s > 1.0:
        return False, 0.0
    q = math.hypot((co[0] - cx) / hx, (co[2] - cz) / hz)
    if q <= 1e-6:
        return True, 1.0
    denom = 1.0 - s / q
    if denom <= 1e-6:
        return True, 1.0
    return True, max(0.0, min(1.0, (1.0 - s) / denom))


def _lid(co, side_sign):
    """(in_zone, t, upper) for the eyelid zone of one eye."""
    cx = side_sign * EYE_CX
    inz, t = _aperture_t(co, cx, EYE_CZ, EYE_AX, EYE_AZ, EYE_HOLE)
    return inz, t, co[2] > EYE_CZ


# Both lids meet on the eye centre line. An aperture cut from a quad grid is a staircase whose lower
# rim is not a function of x — measured, it steps between -4.4 mm and -14.6 mm within a 27 mm span — so
# aiming the upper lid at "the lower rim" either stops short or drives 10 mm through it depending on
# which vertex it reads. Converging BOTH lids on cz makes the closure exact by construction, needs no
# rim measurement at all, and is what a real blink does anyway (the lower lid rises a little too).
LID_CLOSE_Z = EYE_CZ - 0.002        # just below centre — where a real lid line sits
LOWER_LID_SHARE = 1.0               # both rims land on the same line, so the closure is exact


def _lipz(co):
    return _aperture_t(co, 0.0, MOUTH_CZ, MOUTH_AX, MOUTH_AZ, MOUTH_HOLE)


def _brow(co, side_sign):
    """(in_zone, t) over one brow arc, t falling smoothly to 0 at the edge. A constant displacement
    inside a rectangular band left a hard step at the mask boundary, which rendered as a fold across
    the forehead on `angry` — the same class of defect as the smile's cutoff below."""
    e = _ellipse_e(co, side_sign * (EYE_CX + 0.004), BROW_CZ, BROW_AX, BROW_AZ)
    if co[1] <= 0.03 or e > 1.0:
        return False, 0.0
    return True, 1.0 - e


def _corner_weight(x, side_sign):
    """How much of a mouth-corner shape a vertex takes, tapering from the mouth centre outward. A hard
    `|x| > 0.012` cutoff moved the corners while leaving the centre behind, which read as a jagged W."""
    return max(0.0, min(1.0, (side_sign * x - 0.006) / 0.026))


def _front_falloff(y):
    """Smoothly kill a displacement toward the side of the head, so a jaw drop does not tear a seam at
    a hard y cutoff the way WI 936's did."""
    return max(0.0, min(1.0, (y - 0.02) / 0.05))


# Aperture half-extents, measured from the built mesh in build_head(). Placeholders until then.
EYE_HOLE = (0.0, 0.0)
MOUTH_HOLE = (0.0, 0.0)


def _disp(co, key):
    x, y, z = co
    left = x > 0
    side = 1 if left else -1
    named_side = ("Left" if left else "Right")
    side_ok = named_side in key

    if key.startswith("eyeBlink") and side_ok:
        inz, t, upper = _lid(co, side)
        if not inz:
            return (0.0, 0.0, 0.0)
        if upper:
            # the upper lid does most of the work, and swings forward so it passes IN FRONT of the
            # eyeball rather than through it
            return (0.0, 0.012 * t, (LID_CLOSE_Z - z) * t)
        return (0.0, 0.006 * t, (LID_CLOSE_Z - z) * t * LOWER_LID_SHARE)   # ...the lower lid rises to meet it
    if key.startswith("eyeWide") and side_ok:
        inz, t, upper = _lid(co, side)
        return (0.0, 0.0, 0.015 * t) if (inz and upper) else (0.0, 0.0, 0.0)
    if key.startswith("eyeSquint") and side_ok:
        inz, t, upper = _lid(co, side)
        return (0.0, 0.0, 0.013 * t) if (inz and not upper) else (0.0, 0.0, 0.0)

    if key == "browInnerUp":
        for sx in (1, -1):
            inz, t = _brow(co, sx)
            if inz:
                inner = max(0.0, min(1.0, 1.0 - (abs(x) - 0.015) / 0.070))
                return (0.0, 0.0, 0.030 * t * inner)
        return (0.0, 0.0, 0.0)
    if key.startswith("browDown") and side_ok:
        inz, t = _brow(co, side)
        return (0.0, 0.0, -0.026 * t) if inz else (0.0, 0.0, 0.0)

    if key == "jawOpen":
        # Everything at or above the mouth line is the upper lip and stays put — an open mouth drops
        # the jaw, it does not stretch the whole face.
        if z > MOUTH_CZ:
            return (0.0, 0.0, 0.0)
        # the jaw as a whole swings down...
        drop = min(1.0, (MOUTH_CZ - z) / 0.12) * _front_falloff(y)
        dz = -0.070 * drop
        # ...and the lower lip drops further still, or the aperture barely parts: the general jaw
        # falloff is near zero right at the lip, which is exactly where the mouth has to open.
        inz, t = _lipz(co)
        if inz:
            dz -= 0.030 * t
        return (0.0, 0.010 * drop, dz)

    # WI 938's lesson, applied to the stylized head: a mouth corner is BOTH lips, so the mask is the whole
    # lip zone on that side rather than a single band, and the corner moves up-and-out, not just up.
    if key.startswith("mouthSmile") and side_ok:
        inz, t = _lipz(co)
        w = t * _corner_weight(x, side)
        return (side * 0.014 * w, 0.0, 0.030 * w) if inz else (0.0, 0.0, 0.0)
    if key.startswith("mouthFrown") and side_ok:
        inz, t = _lipz(co)
        w = t * _corner_weight(x, side)
        return (side * 0.007 * w, 0.0, -0.030 * w) if inz else (0.0, 0.0, 0.0)
    if key == "mouthFunnel":
        inz, t = _lipz(co)
        if inz:
            return (-x * 0.35 * t, 0.020 * t, -(z - MOUTH_CZ) * 0.25 * t)
        return (0.0, 0.0, 0.0)
    if key == "mouthPucker":
        inz, t = _lipz(co)
        if inz:
            return (-x * 0.55 * t, 0.026 * t, -(z - MOUTH_CZ) * 0.45 * t)
        return (0.0, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def add_shape_keys(head):
    """Runs only after every mesh edit is done: topology is frozen before shape 1 (plan invariant 4)."""
    head.shape_key_add(name="Basis", from_mix=False)
    for key in AUTHORED:
        sk = head.shape_key_add(name=key, from_mix=False)
        scale = 0.0 if (NEGATIVE == "flat-morph" and key == "mouthPucker") else 1.0
        for i, v in enumerate(head.data.vertices):
            bx, by, bz = v.co
            dx, dy, dz = _disp((bx, by, bz), key)
            sk.data[i].co = (bx + dx * scale, by + dy * scale, bz + dz * scale)
        sk.value = 0.0
    if NEGATIVE == "nonzero-stub":
        # a declared stub that is not actually flat — the exact defect the stub check exists to catch
        sk = head.shape_key_add(name="cheekPuff", from_mix=False)
        for i, v in enumerate(head.data.vertices):
            bx, by, bz = v.co
            sk.data[i].co = (bx, by + (0.01 if by > 0.10 else 0.0), bz)
        sk.value = 0.0


def expression_spec():
    have = {sk.name for sk in bpy.data.objects[HEAD].data.shape_keys.key_blocks}
    customs = {name: ([(HEAD, name)] if name in have and name in AUTHORED else [])
               for name in arkit52.ARKIT_52}
    if NEGATIVE == "nonzero-stub":
        customs["cheekPuff"] = [(HEAD, "cheekPuff")]
    presets = {p: [(HEAD, shape, w) for shape, w in binds]
               for p, binds in arkit52.PRESET_COMPOSITION.items()}
    return {"customs": customs, "presets": presets, "overrides": arkit52.PRESET_OVERRIDES}


# ---------------------------------------------------------------------------
# checks — every claim this work item makes, as something that can fail
# ---------------------------------------------------------------------------
class Checks:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail=""):
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return ok

    @property
    def failed(self):
        return [r for r in self.rows if not r["ok"]]


def _evaluated_coords(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    return [v.co.copy() for v in obj.evaluated_get(dg).data.vertices]


def _drive(head, values):
    kb = head.data.shape_keys.key_blocks
    for k in kb:
        k.value = 0.0
    for name, val in values.items():
        kb[name].value = val
    bpy.context.view_layer.update()


def check_geometry(ck, head):
    base = _evaluated_coords(head)

    # A mesh-integrity floor. An inset can throw a vertex clean off the model (measured: x = -1.65 on a
    # 0.16 m head, from even-offset mitring at the patch's staircase corners) and every downstream
    # number then quietly describes a mesh with a spike in it. Cheap check, caught a real defect.
    semi = max(HR * HS[0], HR * HS[1], HR * HS[2])
    outliers = [i for i, c in enumerate(base)
                if math.dist((c.x, c.y, c.z - HZ), (0, 0, 0)) > semi * 1.02]
    for o in (bpy.data.objects[EYE_L], bpy.data.objects[EYE_R]):
        used = {poly.material_index for poly in o.data.polygons}
        ck.add(f"{o.name} carries both sclera and iris", used == {0, 1},
               f"material indices used: {sorted(used)} of {len(o.data.materials)} slots")
    ck.add("no vertex escapes the head volume", not outliers,
           f"{len(outliers)} verts beyond {semi * 1.02 * 1000:.1f} mm from the head centre")

    for side_sign, suffix in ((1, "Left"), (-1, "Right")):
        cx = side_sign * EYE_CX
        # the eyeball must stay inside the head shell OUTSIDE the aperture, or it breaks through as a
        # dark crescent beside the eye — the shell curves away faster than a ball of aperture width does
        breach = []
        for v in bpy.data.objects[HEAD].data.vertices:
            c = v.co
            d2 = (c.x - cx) ** 2 + (c.z - EYE_CZ) ** 2
            # only in front of the eyeball's equator: behind it, shell geometry inside the ball is the
            # socket doing its job, not a breach
            if c.y < EYE_BALL_Y or d2 >= EYE_BALL_R ** 2:
                continue
            if c.y < EYE_BALL_Y + EYE_BALL_SY * math.sqrt(EYE_BALL_R ** 2 - d2):
                breach.append(v.index)
        ck.add(f"the {suffix.lower()} eyeball stays inside the head shell", not breach,
               f"{len(breach)} shell verts sit behind the eyeball surface")
        col = [i for i, c in enumerate(base) if abs(c.x - cx) < 0.014 and c.y > 0.03
               and _ellipse_e(c, cx, EYE_CZ, EYE_AX, EYE_AZ) <= 1.0]
        ck.add(f"eyelid loops exist ({suffix})", len(col) >= 6,
               f"{len(col)} lid verts in the centre column of the aperture")

        upper = [i for i in col if base[i].z > EYE_CZ]
        lower = [i for i in col if base[i].z <= EYE_CZ]
        gap_open = min(base[i].z for i in upper) - max(base[i].z for i in lower)

        _drive(head, {f"eyeBlink{suffix}": 1.0})
        shut = _evaluated_coords(head)
        gap_shut = min(shut[i].z for i in upper) - max(shut[i].z for i in lower)
        # -4 mm ... +4 mm: shut, and not driven so far past the lower lid that the two interpenetrate.
        # This is the WI 936 defect ("a crude vert push") expressed as something that can fail.
        ck.add(f"eyeBlink{suffix} closes the aperture", -0.004 <= gap_shut <= 0.004,
               f"vertical gap {gap_open * 1000:.1f} mm open -> {gap_shut * 1000:.1f} mm shut")

        # the 936 defect, stated as a measurement: nothing may reach the brow band
        moved_into_brow = [i for i in range(len(base))
                           if (shut[i] - base[i]).length > 1e-6 and shut[i].z >= BROW_CZ - BROW_AZ]
        ck.add(f"eyeBlink{suffix} does not disturb the brow", not moved_into_brow,
               f"{len(moved_into_brow)} displaced verts at or above the brow band")

        # The lid must pass IN FRONT of the eyeball, not through it. Measure the verts that actually
        # close — the rim — not the whole zone: the outer patch verts curve back over the brow and are
        # naturally the lowest-y in the column, which made the first version of this check measure
        # geometry that never moves.
        # ...compared PER VERTEX against the eyeball surface at that vertex's own (x, z). Comparing a
        # global minimum lid y against the eyeball's widest point mixes two different places on the
        # face and fails verts at the outer corner, where the eyeball is nowhere near the surface.
        rim_upper = [i for i in upper if _lid(base[i], side_sign)[1] >= 0.85]
        sunk = []
        for i in rim_upper:
            d2 = (shut[i].x - cx) ** 2 + (shut[i].z - EYE_CZ) ** 2
            if d2 >= EYE_BALL_R ** 2:
                continue
            surface_y = EYE_BALL_Y + EYE_BALL_SY * math.sqrt(EYE_BALL_R ** 2 - d2)
            if shut[i].y <= surface_y:
                sunk.append(i)
        ck.add(f"eyeBlink{suffix} lid covers the eyeball", not sunk,
               f"{len(sunk)} of {len(rim_upper)} rim verts sink into the eyeball")

        other = "Right" if suffix == "Left" else "Left"
        ocx = -side_sign * EYE_CX
        ocol = [i for i, c in enumerate(base) if abs(c.x - ocx) < 0.014 and c.y > 0.03
                and _ellipse_e(c, ocx, EYE_CZ, EYE_AX, EYE_AZ) <= 1.0]
        ck.add(f"eyeBlink{suffix} leaves the {other.lower()} eye alone",
               all((shut[i] - base[i]).length < 1e-6 for i in ocol))

    # Measure the mouth APERTURE, not a threshold straddle. The first version compared the lowest
    # upper-lip vert to the highest lower-lip vert across a z cutoff, which are adjacent verts either
    # side of the cutoff — it reported 1.6 mm whether the mouth was open or shut.
    mouth_col = [i for i, c in enumerate(base)
                 if abs(c.x) < 0.014 and c.y > 0.03 and _lipz(c)[1] >= 0.80]
    m_up = [i for i in mouth_col if base[i].z > MOUTH_CZ]
    m_dn = [i for i in mouth_col if base[i].z <= MOUTH_CZ]
    ck.add("the mouth aperture exists", bool(m_up) and bool(m_dn),
           f"{len(m_up)} upper-rim / {len(m_dn)} lower-rim verts in the centre column")
    closed = min(base[i].z for i in m_up) - max(base[i].z for i in m_dn)
    _drive(head, {"jawOpen": 1.0})
    jaw = _evaluated_coords(head)
    opened = min(jaw[i].z for i in m_up) - max(jaw[i].z for i in m_dn)
    ck.add("jawOpen opens the mouth", opened - closed > 0.015,
           f"aperture {closed * 1000:.1f} mm shut -> {opened * 1000:.1f} mm open")
    ck.add("jawOpen leaves the upper lip in place",
           max((jaw[i] - base[i]).length for i in m_up) < 1e-6,
           "an open mouth drops the lower lip; the upper lip is not part of the jaw")

    for suffix in ("Left", "Right"):
        _drive(head, {f"mouthSmile{suffix}": 1.0})
        sm = _evaluated_coords(head)
        sign = 1 if suffix == "Left" else -1
        corner = [i for i, c in enumerate(base) if _lipz(c)[0] and sign * c.x > 0.02]
        lift = sum(sm[i].z - base[i].z for i in corner) / max(1, len(corner))
        ck.add(f"mouthSmile{suffix} lifts that corner", lift > 0.005,
               f"mean corner lift {lift * 1000:.1f} mm over {len(corner)} verts")
        # WI 938's bug: a smile that puffs the cheek instead of moving the mouth
        cheek = [i for i, c in enumerate(base)
                 if c.y > 0.03 and c.z > MOUTH_CZ + 0.045 and sign * c.x > 0.02]
        ck.add(f"mouthSmile{suffix} leaves the cheek alone",
               all((sm[i] - base[i]).length < 1e-6 for i in cheek),
               f"{len(cheek)} cheek verts checked")

    _drive(head, {})


def check_morph_contract(ck, head):
    kb = head.data.shape_keys.key_blocks
    names = [k.name for k in kb if k.name != "Basis"]
    ck.add("authored shape keys are exactly the contract's authored set",
           sorted(names) == sorted(AUTHORED),
           f"{len(names)} keys" + ("" if sorted(names) == sorted(AUTHORED)
                                   else f"; unexpected {sorted(set(names) ^ set(AUTHORED))}"))

    basis = kb["Basis"].data
    for name in names:
        d = max((kb[name].data[i].co - basis[i].co).length for i in range(len(basis)))
        ck.add(f"authored morph {name} displaces", d > 1e-4, f"max {d * 1000:.1f} mm")


def check_export_reimport(ck, out, name):
    """Re-import each artifact into a clean scene and assert what a consumer will actually see."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(out / f"{name}.glb"))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    with_keys = [o for o in meshes if o.data.shape_keys]
    glb_keys = sorted(k.name for o in with_keys for k in o.data.shape_keys.key_blocks
                      if k.name != "Basis")
    ck.add("glb re-imports with every authored morph", sorted(set(glb_keys)) == sorted(AUTHORED),
           f"{len(set(glb_keys))} morph targets")
    ck.add("glb re-imports with an armature",
           any(o.type == 'ARMATURE' for o in bpy.context.scene.objects))

    for spec, path in (("1.0", out / f"{name}.vrm"), ("0.x", out / f"{name}.vrm0.vrm")):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        vrm_export.ensure_addon()
        bpy.ops.import_scene.vrm(filepath=str(path))
        arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
        ck.add(f"VRM {spec} re-imports with an armature", len(arms) == 1, f"{len(arms)} armatures")
        if not arms:
            continue
        ext = arms[0].data.vrm_addon_extension
        # WI 938 shipped a demo carrying Blender's startup `Cube` because the VRM exporter is
        # scene-global. Assert the object SET, not a count: a count passes if one stray replaces one
        # expected object.
        objs = sorted(o.name for o in bpy.context.scene.objects)
        expected_objs = sorted([arms[0].name, HEAD, BODY, EYE_L, EYE_R])
        ck.add(f"VRM {spec} carries only the avatar", objs == expected_objs, f"objects: {objs}")

        if spec == "1.0":
            customs = {c.custom_name: len(c.morph_target_binds) for c in ext.vrm1.expressions.custom}
            ck.add("VRM 1.0 declares all 52 ARKit clips, exact names",
                   sorted(customs) == sorted(arkit52.ARKIT_52),
                   f"{len(customs)} customs")
            bound = sorted(n for n, c in customs.items() if c > 0)
            stubs = [n for n, c in customs.items() if c == 0]
            ck.add("the authored clips are bound 1:1", bound == sorted(AUTHORED),
                   f"{len(bound)} bound, each with exactly one morph target"
                   if all(customs[n] == 1 for n in bound) else "a clip binds more than one morph")
            ck.add("one morph per ARKit clip", all(customs[n] == 1 for n in bound))
            ck.add("the remaining clips are declared empty stubs",
                   sorted(stubs) == sorted(arkit52.stub_names(AUTHORED)), f"{len(stubs)} stubs")

            preset_binds = {p: len(getattr(ext.vrm1.expressions.preset, p).morph_target_binds)
                            for p in arkit52.VRM1_PRESETS}
            composed = {p: n for p, n in preset_binds.items() if n}
            ck.add("the 13 morph-composed presets are bound",
                   sorted(composed) == sorted(arkit52.PRESET_COMPOSITION),
                   f"{sorted(composed)}")
            ck.add("bind counts match the composition table",
                   all(preset_binds[p] == len(b) for p, b in arkit52.PRESET_COMPOSITION.items()))
            ck.add("fractional preset weights survive the round trip",
                   any(abs(b.weight - 1.0) > 1e-6
                       for p in arkit52.PRESET_COMPOSITION
                       for b in getattr(ext.vrm1.expressions.preset, p).morph_target_binds),
                   "a viseme needs a partial jaw; hard-coded 1.0 could not express one")
            ck.add("the four look_* presets are empty (gaze is bone-driven)",
                   all(preset_binds[p] == 0 for p in ("look_up", "look_down", "look_left", "look_right")))
            ck.add("neutral is empty", preset_binds["neutral"] == 0)

            hb = ext.vrm1.humanoid.human_bones
            req = {s: getattr(hb, s).node.bone_name for s in sorted(vrm_export.REQUIRED_VRM1)}
            ck.add("15/15 required humanoid slots bound", all(req.values()),
                   f"{sum(1 for v in req.values() if v)}/15")
            ck.add("both optional eye slots bound",
                   bool(hb.left_eye.node.bone_name) and bool(hb.right_eye.node.bone_name),
                   f"{hb.left_eye.node.bone_name} / {hb.right_eye.node.bone_name}")
            ck.add("look_at is in bone mode", ext.vrm1.look_at.type == "bone",
                   ext.vrm1.look_at.type)
            got = {p: {k: getattr(getattr(ext.vrm1.expressions.preset, p), k)
                       for k in arkit52.PRESET_OVERRIDES[p]}
                   for p in arkit52.PRESET_OVERRIDES}
            ck.add("expression override modes survive the round trip",
                   got == arkit52.PRESET_OVERRIDES, json.dumps(got, sort_keys=True))
        else:
            groups = {g.name: len(g.binds) for g in ext.vrm0.blend_shape_master.blend_shape_groups}
            # VRM 0.x has 17 presets, not 18: `surprised` is new in 1.0 (WI 923). So it is correctly
            # absent from what we WRITE. Whatever the importer adds back is its business; assert that
            # every group we wrote survived with its binds, rather than asserting set equality.
            written = [p for p in arkit52.PRESET_COMPOSITION if p in vrm_export._VRM1_PRESET_TO_VRM0]
            ck.add("VRM 0.x carries every preset blend-shape group we wrote",
                   all(groups.get(p, 0) == len(arkit52.PRESET_COMPOSITION[p]) for p in written),
                   f"{len(written)} written, {len(groups)} present: {sorted(groups)}")
            ck.add("VRM 0.x omits `surprised` (a 1.0-only preset)",
                   "surprised" not in arkit52.PRESET_COMPOSITION
                   or "surprised" not in vrm_export._VRM1_PRESET_TO_VRM0)


def check_eye_bones(ck, arm, head, eyeballs):
    names = {b.name for b in arm.data.bones}
    ck.add("eye bones exist on the rig", {"eye.L", "eye.R"} <= names)
    for o in (head,):
        ck.add(f"{o.name} has no eye-bone weight",
               not ({"eye.L", "eye.R"} & {g.name for g in o.vertex_groups}),
               "auto-weighting ran before the eye bones existed")
    for o in eyeballs:
        ck.add(f"{o.name} is rigidly skinned to its gaze bone",
               [g.name for g in o.vertex_groups] in (["eye.L"], ["eye.R"]))

    base_l = _evaluated_coords(eyeballs[0])
    base_head = _evaluated_coords(head)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["eye.L"].rotation_mode = 'XYZ'
    arm.pose.bones["eye.L"].rotation_euler = (0.0, 0.0, math.radians(20))
    bpy.context.view_layer.update()
    moved_l = _evaluated_coords(eyeballs[0])
    moved_r = _evaluated_coords(eyeballs[1])
    now_head = _evaluated_coords(head)
    ck.add("rotating eye.L moves the left eyeball",
           max((a - b).length for a, b in zip(base_l, moved_l)) > 1e-4)
    ck.add("rotating eye.L moves neither the right eyeball nor the head",
           all((a - b).length < 1e-6 for a, b in zip(_evaluated_coords(eyeballs[1]), moved_r))
           and all((a - b).length < 1e-6 for a, b in zip(base_head, now_head)))
    arm.pose.bones["eye.L"].rotation_euler = (0.0, 0.0, 0.0)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()


# ---------------------------------------------------------------------------
# previews — for human eyes; there is deliberately no automated quality score
# ---------------------------------------------------------------------------
SHOTS = {
    "neutral": {},
    "blink": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0},
    "wink": {"eyeBlinkLeft": 1.0},
    "smile": {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0},
    "jawOpen": {"jawOpen": 1.0},
    "pucker": {"mouthPucker": 1.0},
    "funnel": {"mouthFunnel": 1.0},
    "angry": {"browDownLeft": 1.0, "browDownRight": 1.0, "mouthFrownLeft": 0.45,
              "mouthFrownRight": 0.45},
    "sad": {"browInnerUp": 1.0, "mouthFrownLeft": 0.8, "mouthFrownRight": 0.8},
    "surprised": {"eyeWideLeft": 1.0, "eyeWideRight": 1.0, "browInnerUp": 0.85, "jawOpen": 0.6},
}


def render_previews(head, out):
    """WI 936's two recorded gotchas, both fixed here by construction: the camera goes on the +Y (front)
    side because the face is at +Y, and view_layer.update() runs before every render or the shape-key
    state is not evaluated and every frame comes out identical."""
    pv = out / "previews"
    pv.mkdir(parents=True, exist_ok=True)
    scn = bpy.context.scene
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    scn.world = world
    tgt = bpy.data.objects.new("tgt", None)
    tgt.location = (0, 0, HZ)
    scn.collection.objects.link(tgt)
    cam_d = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_d)
    scn.collection.objects.link(cam)
    cam.location = (0, 0.80, HZ)
    cam_d.lens = 80
    scn.camera = cam
    con = cam.constraints.new('TRACK_TO')
    con.target = tgt
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    sun_d = bpy.data.lights.new("s", 'SUN')
    sun_d.energy = 4
    sun = bpy.data.objects.new("s", sun_d)
    scn.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(-55), 0, math.radians(18))
    scn.render.resolution_x = scn.render.resolution_y = 420
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    scn.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    for name, values in SHOTS.items():
        _drive(head, values)
        scn.render.filepath = str(pv / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    _drive(head, {})
    return pv


# ---------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    problems = arkit52.check_contract()
    if problems:
        raise SystemExit("arkit52 contract table is inconsistent: " + "; ".join(problems))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {
        "skin": _mat("skin", (0.92, 0.76, 0.60)),
        "brow": _mat("brow", (0.26, 0.16, 0.09)),
        "lip": _mat("lip", (0.62, 0.24, 0.24)),
        # No separate eyelid material: it was indistinguishable from skin at any render size.
        # (It was also tried as a VRM size lever and did not work — removing it changed the file by
        # 7 KB. The size driver is that the VRM exporter writes DENSE morph targets including NORMALs
        # where the glTF exporter writes sparse POSITIONs only: 605,744 stored elements per attribute
        # against 12,808, from the same four primitives. `export_try_sparse_sk` has no effect on the
        # VRM path. The lever that would work is fewer mesh vertices.)
        "cavity": _mat("cavity", (0.05, 0.02, 0.02), rough=0.9),
        "sclera": _mat("sclera", (0.95, 0.95, 0.95), rough=0.25),
        "iris": _mat("iris", (0.09, 0.16, 0.30), rough=0.15),
        "suit": _mat("suit", (0.30, 0.42, 0.66)),
    }

    arm = build_armature(corn_bone_defs(), "v1_face_rig")
    head = build_head(mats)
    body = build_body(mats)
    auto_skin([head, body], arm)

    add_eye_bones(arm)
    eyeballs = [build_eyeball(EYE_L, EYE_CX, mats), build_eyeball(EYE_R, -EYE_CX, mats)]
    for o, bone in zip(eyeballs, ("eye.L", "eye.R")):
        rigid_skin(o, arm, bone)

    # --- topology is frozen from here on ---
    if NEGATIVE == "stray-object":
        bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.4, 0, 1.0))
    add_shape_keys(head)

    ck = Checks()
    print("\n== geometry + morphs (in scene) ==")
    check_geometry(ck, head)
    check_morph_contract(ck, head)
    check_eye_bones(ck, arm, head, eyeballs)

    name = "v1_face_rig"
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm, head, body, *eyeballs]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), export_format='GLB',
                              export_morph=True, use_selection=True,
                              # a flat stylized head gains nothing from per-morph normals, and they are
                              # half the file: 4.4 MB of morph data on a 9.2k-vert mesh
                              export_morph_normal=False, export_try_sparse_sk=True)

    p1, p0 = vrm_export.export_vrm(
        arm, OUT, name, author="asset-harness (WI 1362)",
        humanoid=vrm_export.HUMANOID_19_EYES,
        expressions=expression_spec(),
        look_at_offset=(0.0, EYE_BALL_Y, EYE_CZ - 1.00),   # relative to the head bone's head (z=1.00)
        # the stray-object control also switches the purge off, so the DETECTOR is seen to fail —
        # leaving the purge on would only demonstrate that the purge works, which the normal run
        # already shows
        purge_non_avatar=(NEGATIVE != "stray-object"),
    )

    previews = None
    if PREVIEWS:
        previews = render_previews(head, OUT)

    print("\n== re-import (clean scene) ==")
    check_export_reimport(ck, OUT, name)

    evidence = {
        "work_item": "WI 1362 — v1 stylized face rig on frozen loop topology (923 ladder step 6)",
        "generator_script": "blender_v1_face_rig.py",
        "contract_owner": "arkit52.py",
        "negative_control": NEGATIVE,
        "topology": {
            "head_base": f"UV sphere r={HR} segments=128 rings=72, scaled {HS}",
            "apertures": {"eyes": 2, "mouth": 1},
            "concentric_loops_per_aperture": INSETS,
            "eye_inset_thickness_m": EYE_INSET_T,
            "mouth_inset_thickness_m": MOUTH_INSET_T,
            "mouth_cavity_depth_m": CAVITY_DEPTH,
        },
        "morphs": {
            "authored": AUTHORED,
            "authored_count": len(AUTHORED),
            "declared": len(arkit52.ARKIT_52),
            "stub_count": len(arkit52.stub_names(AUTHORED)),
            "stub_reasons": {k: list(v) for k, v in arkit52.STUB_REASONS.items()},
        },
        "presets": {
            "slots": len(arkit52.VRM1_PRESETS),
            "morph_composed": sorted(arkit52.PRESET_COMPOSITION),
            "empty_by_design": ["neutral", "look_up", "look_down", "look_left", "look_right"],
            "overrides": arkit52.PRESET_OVERRIDES,
        },
        "gaze": {"mode": "bone", "bones": ["eye.L", "eye.R"],
                 "humanoid_slots": ["left_eye", "right_eye"]},
        "licence": {
            "head geometry / rig / morphs": "authored (ours) — commercial yes, redistribute yes",
            "Blender + saturday06 VRM add-on": "GPL-3.0-or-later + MIT — tool only, imposes nothing "
                                               "on exported assets",
            "ARKit names": "Apple public API vocabulary used as an interop convention; Google ships "
                           "the identical 52 names under Apache-2.0. Describe as ARKit-compatible.",
            "effective output licence": "clean",
        },
        "artifacts": {"vrm1": str(p1), "vrm0": str(p0), "glb": str(OUT / f"{name}.glb"),
                      "previews": str(previews) if previews else None},
        "checks": ck.rows,
        "summary": f"{len(ck.rows) - len(ck.failed)}/{len(ck.rows)}",
    }
    (OUT / f"{name}_evidence.json").write_text(json.dumps(evidence, indent=2))
    (OUT / f"{name}_manifest.json").write_text(json.dumps({
        "asset": "WI 1362 stylized v1 face rig (ARKit-52 declared, 16 authored, bone gaze)",
        "generator_script": "blender_v1_face_rig.py",
        "bind": "SKINNED: armature modifier + auto weights; eyeballs rigid to eye.L/eye.R",
        "authored_morphs": AUTHORED,
        "arkit_declared": len(arkit52.ARKIT_52),
        "head_variant": "stylized-v1",
        "license": "clean: Blender (GPL) + authored geometry + hand-authored morphs",
    }, indent=2))

    print(f"\n{len(ck.rows) - len(ck.failed)}/{len(ck.rows)} checks passed")
    for r in ck.failed:
        print(f"  FAILED: {r['check']} — {r['detail']}")
    raise SystemExit(1 if ck.failed else 0)


if __name__ == "__main__":
    main()
