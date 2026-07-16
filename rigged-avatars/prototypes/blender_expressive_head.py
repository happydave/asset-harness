#!/usr/bin/env python3
"""WI 936: a stylized, readable **expressive head** — the first real cut of the stylized head archetype
(WI 923 ladder step 5), and a proper demo avatar for the WI 934/935 VRM inspector (corn has no morphs;
the WI 926 face_spike is a crude sphere).

    ~/blender-4.2/blender --background --python blender_expressive_head.py -- --out DIR [--previews]

A skinned Kerbal-tier head on the 19-bone humanoid rig, carrying ~14 authored ARKit morphs (blinks, eye
wide/squint, brows, jaw, smile/frown) with the **full ARKit-52 declared as expression clips** (unauthored =
empty Perfect-Sync stubs). Eyes/brows/mouth are material-distinct regions ON the single deformable head
mesh, so the morphs move recognizable features. Exports VRM 1.0 + 0.x + game .glb via the shared
vrm_export.py. Clean licence (Blender primitives + hand-authored morphs).

--previews renders front views of a few expressions to DIR/previews/ for readability self-check.
"""
import bpy, sys, json, math
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/expressive_head")
OUT.mkdir(parents=True, exist_ok=True)
PREVIEWS = "--previews" in argv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_corn import corn_bone_defs, build_armature
import vrm_export

HEAD = "face"
BODY = "torso"

# ---- ARKit-52 (exact camelCase) --------------------------------------------
ARKIT_52 = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft",
    "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
    "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "noseSneerLeft", "noseSneerRight", "tongueOut",
]
AUTHORED = [
    "eyeBlinkLeft", "eyeBlinkRight", "eyeWideLeft", "eyeWideRight", "eyeSquintLeft", "eyeSquintRight",
    "browInnerUp", "browDownLeft", "browDownRight", "jawOpen",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
]

# ---- head frame (world/armature space, +Y front) ---------------------------
HZ = 1.15            # head centre z
EYE_Z = 1.19        # eye band centre
EYE_DX = 0.075      # eye centre |x|
EYE_R = 0.045       # eye half-extent
BROW_Z = 1.245      # brow band
MOUTH_Z = 1.055     # mouth band centre
MOUTH_HALFW = 0.075


def _mat(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.6
    return m


def _region(co):
    """Classify a face-centroid coordinate into a material region."""
    x, y, z = co
    if y <= 0.02:
        return "skin"
    left = x > 0
    ax = abs(x)
    # eyes: two almond bands
    if EYE_Z - EYE_R <= z <= EYE_Z + EYE_R and EYE_DX - EYE_R <= ax <= EYE_DX + EYE_R:
        return "eyeL" if left else "eyeR"
    # brows: a band above the eyes
    if BROW_Z - 0.02 <= z <= BROW_Z + 0.02 and 0.02 <= ax <= EYE_DX + EYE_R:
        return "brow"
    # mouth: a lower-front band
    if MOUTH_Z - 0.02 <= z <= MOUTH_Z + 0.025 and ax <= MOUTH_HALFW:
        return "mouth"
    return "skin"


def build_head(arm):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.16, location=(0, 0, HZ), segments=40, ring_count=28)
    o = bpy.context.active_object; o.name = HEAD
    o.scale = (1.0, 0.98, 1.14); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mats = {
        "skin": _mat("skin", (0.90, 0.74, 0.58)),
        "eyeL": _mat("eye", (0.07, 0.07, 0.10)), "eyeR": _mat("eye2", (0.07, 0.07, 0.10)),
        "brow": _mat("brow", (0.28, 0.18, 0.10)), "mouth": _mat("mouth", (0.45, 0.16, 0.16)),
    }
    slot = {}
    for k, m in mats.items():
        o.data.materials.append(m); slot[k] = len(o.data.materials) - 1
    me = o.data
    for poly in me.polygons:
        c = poly.center
        poly.material_index = slot[_region((c.x, c.y, c.z))]
    return o


def build_body(arm):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.19, location=(0, 0, 0.72), segments=20, ring_count=14)
    o = bpy.context.active_object; o.name = BODY
    o.scale = (1.0, 0.7, 1.9); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(_mat("suit", (0.30, 0.42, 0.66)))
    return o


# ---- morph displacements (per authored key) --------------------------------
def _disp(co, key):
    x, y, z = co
    if y <= 0.03:
        return (0.0, 0.0, 0.0)
    left = x > 0
    ax = abs(x)
    in_eye = (EYE_Z - EYE_R - 0.02 <= z <= EYE_Z + EYE_R + 0.02) and (EYE_DX - EYE_R - 0.01 <= ax <= EYE_DX + EYE_R + 0.01)
    side_ok = (left and "Left" in key) or ((not left) and "Right" in key)

    if key.startswith("eyeBlink") and in_eye and side_ok and z > EYE_Z:
        return (0.0, 0.0, -(z - (EYE_Z - EYE_R)))          # upper lid drops to lower lid → eye closes
    if key.startswith("eyeWide") and in_eye and side_ok and z > EYE_Z:
        return (0.0, 0.0, 0.018)                            # upper lid lifts → eye widens
    if key.startswith("eyeSquint") and in_eye and side_ok and z < EYE_Z:
        return (0.0, 0.0, 0.016)                            # lower lid raises → squint
    if key == "browInnerUp" and BROW_Z - 0.03 <= z <= BROW_Z + 0.03 and ax <= EYE_DX:
        return (0.0, 0.0, 0.022 * (1.0 - ax / EYE_DX))      # inner brows up
    if key.startswith("browDown") and side_ok and BROW_Z - 0.03 <= z <= BROW_Z + 0.03 and 0.02 <= ax <= EYE_DX + EYE_R:
        return (0.0, 0.0, -0.022)                           # brow lowers
    if key == "jawOpen" and z <= MOUTH_Z + 0.03:
        drop = min(1.0, (MOUTH_Z + 0.03 - z) / 0.14)
        return (0.0, 0.01 * drop, -0.075 * drop)            # lower face drops + juts → mouth opens
    if key.startswith("mouthSmile") and side_ok and abs(z - MOUTH_Z) <= 0.03 and 0.02 <= ax <= MOUTH_HALFW + 0.02:
        return (0.012, 0.0, 0.028)                          # corner lifts + widens
    if key.startswith("mouthFrown") and side_ok and abs(z - MOUTH_Z) <= 0.03 and 0.02 <= ax <= MOUTH_HALFW + 0.02:
        return (0.006, 0.0, -0.028)                         # corner drops
    return (0.0, 0.0, 0.0)


def add_shape_keys(head):
    head.shape_key_add(name="Basis", from_mix=False)
    for key in AUTHORED:
        sk = head.shape_key_add(name=key, from_mix=False)
        for i, v in enumerate(head.data.vertices):
            bx, by, bz = v.co
            dx, dy, dz = _disp((bx, by, bz), key)
            sk.data[i].co = (bx + dx, by + dy, bz + dz)
        sk.value = 0.0
    return list(AUTHORED)


def skin(meshes, arm):
    bpy.ops.object.select_all(action='DESELECT')
    for m in meshes:
        m.select_set(True)
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')


def expression_spec():
    authored = {k: [(HEAD, k)] for k in AUTHORED}
    customs = {name: authored.get(name, []) for name in ARKIT_52}   # 14 bound, 38 empty stubs
    presets = {
        "blink": [(HEAD, "eyeBlinkLeft"), (HEAD, "eyeBlinkRight")],
        "happy": [(HEAD, "mouthSmileLeft"), (HEAD, "mouthSmileRight")],
        "angry": [(HEAD, "browDownLeft"), (HEAD, "browDownRight")],
        "sad": [(HEAD, "mouthFrownLeft"), (HEAD, "mouthFrownRight"), (HEAD, "browInnerUp")],
        "aa": [(HEAD, "jawOpen")],
        "surprised": [(HEAD, "eyeWideLeft"), (HEAD, "eyeWideRight"), (HEAD, "browInnerUp"), (HEAD, "jawOpen")],
        "relaxed": [(HEAD, "mouthSmileLeft"), (HEAD, "mouthSmileRight"), (HEAD, "eyeSquintLeft"), (HEAD, "eyeSquintRight")],
    }
    return {"customs": customs, "presets": presets}


def render_previews(head):
    """Render FRONT views (the face is at +Y) of a few expressions to OUT/previews/ for a readability
    self-check. Camera on the +Y side, tracked to the head; view_layer.update() before each render so the
    shape-key state is evaluated (both were bugs in the first cut: camera saw the -Y back, and un-updated
    renders were identical)."""
    pv = OUT / "previews"; pv.mkdir(exist_ok=True)
    scn = bpy.context.scene
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    scn.world = world
    tgt = bpy.data.objects.new("tgt", None); tgt.location = (0, 0, HZ); scn.collection.objects.link(tgt)
    cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d)
    scn.collection.objects.link(cam); cam.location = (0, 0.95, HZ); cam_d.lens = 70; scn.camera = cam
    con = cam.constraints.new('TRACK_TO'); con.target = tgt
    con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
    sun_d = bpy.data.lights.new("s", 'SUN'); sun_d.energy = 4
    sun = bpy.data.objects.new("s", sun_d); scn.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(-55), 0, math.radians(18))   # from front, slightly above
    scn.render.resolution_x = scn.render.resolution_y = 360
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    scn.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    kb = head.data.shape_keys.key_blocks
    shots = {"neutral": [], "blink": [("eyeBlinkLeft", 1), ("eyeBlinkRight", 1)],
             "smile": [("mouthSmileLeft", 1), ("mouthSmileRight", 1)],
             "jawOpen": [("jawOpen", 1)], "angry": [("browDownLeft", 1), ("browDownRight", 1)],
             "surprised": [("eyeWideLeft", 1), ("eyeWideRight", 1), ("browInnerUp", 1), ("jawOpen", 0.7)]}
    for name, sets in shots.items():
        for k in kb:
            k.value = 0.0
        for sk, val in sets:
            kb[sk].value = val
        bpy.context.view_layer.update()
        scn.render.filepath = str(pv / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    for k in kb:
        k.value = 0.0


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = build_armature(corn_bone_defs(), "head_rig")
    head = build_head(arm)
    body = build_body(arm)
    keys = add_shape_keys(head)
    skin([head, body], arm)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(OUT / "expressive_head.glb"), export_format='GLB',
                              export_morph=True, use_selection=True)

    p1, p0 = vrm_export.export_vrm(arm, OUT, "expressive_head", author="asset-harness (WI 936)",
                                   expressions=expression_spec())
    (OUT / "expressive_head_manifest.json").write_text(json.dumps({
        "asset": "WI 936 stylized expressive head (ARKit-52 declared, ~14 authored)",
        "generator_script": "blender_expressive_head.py",
        "bind": "SKINNED: armature modifier + auto weights",
        "authored_morphs": AUTHORED, "arkit_declared": len(ARKIT_52),
        "license": "clean: Blender (GPL) + authored geometry + hand-authored morphs",
    }, indent=2))
    print(f"built expressive head: {OUT/'expressive_head.glb'}, {p1}, {p0}")
    if PREVIEWS:
        render_previews(head)
        print(f"rendered previews to {OUT/'previews'}")


if __name__ == "__main__":
    main()
