"""WI 938 — SPIKE: ARKit morphs on the MPFB2 CC0 realistic head (de-risks WI 930).

Proves the MPFB2 realistic head *topology* can carry ARKit-named shape keys that deform convincingly, and
that they export through the existing `vrm_export.py` unchanged. This is the unblocked slice of WI 930 (the
realistic head archetype); it does NOT resolve FLAME/dense-topology substrate, near-full 52-shape authoring,
head isolation, or the realistic texture lane — those stay with 930.

Authoring method — **weight-mask displacement**: MPFB's `default` rig imports a vertex group per facial bone
(`jaw`, `orbicularis03.L/R` eyelids, `risorius03.L/R` mouth corners). Those groups say *which* verts belong
to a feature and give a smooth falloff; we displace them in a controlled world direction to sculpt each shape
key. This leverages MPFB's anatomy (unavailable on the WI 936 smooth sphere) without fragile bone-pose math.

Run (on ai2, MPFB2 extension installed per WI 927):
    ~/blender-4.2/blender --background --python blender_realistic_head_spike.py -- --out ~/rhead/out

Requires `vrm_export.py` importable (same dir or sys.path). Emits VRM 1.0 + 0.x + glb + evidence JSON +
head-framed preview renders.
"""

import importlib
import sys
import os
import json

import bpy
import mathutils


def dynamic_import(pkg, key):
    for m in sys.modules:
        if m.endswith(pkg):
            mod = importlib.import_module(m)
            if not hasattr(mod, key):
                raise AttributeError(f"{m} lacks {key}")
            return getattr(mod, key)
    raise ValueError(f"no module ending in {pkg}")


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.expanduser("~/rhead/out")
    if "--out" in argv:
        out = os.path.expanduser(argv[argv.index("--out") + 1])
    return out


# default MPFB rig -> VRM humanoid (probed live on ai2, WI 938). Covers all 15 required VRM1 slots.
HUMANOID_MPFB_DEFAULT = {
    "root": ("hips", "hips"), "spine05": ("spine", "spine"), "spine03": ("chest", "chest"),
    "neck01": ("neck", "neck"), "head": ("head", "head"),
    "clavicle.L": ("left_shoulder", "leftShoulder"), "upperarm01.L": ("left_upper_arm", "leftUpperArm"),
    "lowerarm01.L": ("left_lower_arm", "leftLowerArm"), "wrist.L": ("left_hand", "leftHand"),
    "clavicle.R": ("right_shoulder", "rightShoulder"), "upperarm01.R": ("right_upper_arm", "rightUpperArm"),
    "lowerarm01.R": ("right_lower_arm", "rightLowerArm"), "wrist.R": ("right_hand", "rightHand"),
    "upperleg01.L": ("left_upper_leg", "leftUpperLeg"), "lowerleg01.L": ("left_lower_leg", "leftLowerLeg"),
    "foot.L": ("left_foot", "leftFoot"),
    "upperleg01.R": ("right_upper_leg", "rightUpperLeg"), "lowerleg01.R": ("right_lower_leg", "rightLowerLeg"),
    "foot.R": ("right_foot", "rightFoot"),
}


def _group_weights(obj, group_name):
    """{vertex_index: weight} for one vertex group, or {} if the group is absent."""
    vg = obj.vertex_groups.get(group_name)
    if vg is None:
        return {}
    gi = vg.index
    out = {}
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == gi and g.weight > 0.0:
                out[v.index] = g.weight
    return out


def _group_centroid_x(obj, weights):
    if not weights:
        return 0.0
    return sum(obj.data.vertices[vi].co.x * w for vi, w in weights.items()) / sum(weights.values())


# Each ARKit morph = list of (vertex_group, world_direction, scale_metres). "outward" in x is resolved per
# group from its centroid so left/right corners pull away from the face midline regardless of rig convention.
def _morph_specs(obj):
    def sx(group):  # +1 if the group sits on +x side, else -1
        return 1.0 if _group_centroid_x(obj, _group_weights(obj, group)) >= 0 else -1.0
    # Amplitudes are deliberately exaggerated for legibility (a spike demo); real WI 930 would calibrate to
    # ARKit reference blendshape amplitudes. NOTE the two techniques (WI 938 finding): localized shapes
    # (blink, smile) sculpt cleanly as single-group weight-mask displacements, but jawOpen does NOT — the
    # mouth-opening is skinned to the lip (oris) bones, not the jaw group, so jawOpen is baked from a jaw
    # BONE pose instead (see _bake_bone_shapekey), letting MPFB's skinning carry the lips open.
    return {
        "eyeBlinkLeft": [("orbicularis03.L", (0.0, 0.0, -1.0), 0.016)],
        "eyeBlinkRight": [("orbicularis03.R", (0.0, 0.0, -1.0), 0.016)],
        "mouthSmileLeft": [("risorius03.L", (sx("risorius03.L") * 0.6, 0.0, 1.0), 0.022)],
        "mouthSmileRight": [("risorius03.R", (sx("risorius03.R") * 0.6, 0.0, 1.0), 0.022)],
    }


def _bake_bone_shapekey(mesh, arm, sk_name, bone_name, angle=0.5):
    """Bake a facial-bone pose into a named shape key. Used for jawOpen: rotating the `jaw` bone opens the
    mouth correctly because MPFB skins the lips to it — something a single weight-group displacement can't
    reproduce. Rotation sign is auto-detected (the one that lowers the chin/tail). Returns (max_disp, 1).

    The morph is the **posed-minus-rest** evaluated delta, NOT `modifier_apply_as_shapekey`. That operator
    stores the fully-evaluated mesh absolutely, which on an MPFB character silently includes the active
    macro-detail shape keys (`$md-…` age/gender/proportions) — so the jawOpen shape key would carry the
    whole-body proportioning and morph the entire body at weight 1 (WI 938 owner review found this). Taking
    (posed_eval − rest_eval) with the macros active in both cancels them, leaving only the jaw articulation
    (verified: body verts move ~0). Non-armature modifiers are disabled during eval so the evaluated vertex
    count matches the base mesh."""
    armmod = next((m for m in mesh.modifiers if m.type == "ARMATURE"), None)
    if armmod is None or bone_name not in arm.pose.bones:
        return (0.0, 0)
    if mesh.data.shape_keys is None:
        mesh.shape_key_add(name="Basis", from_mix=False)
    basis = mesh.data.shape_keys.key_blocks["Basis"]

    saved = [(m, m.show_viewport) for m in mesh.modifiers if m.type != "ARMATURE"]
    for m, _ in saved:
        m.show_viewport = False

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    pb = arm.pose.bones[bone_name]
    pb.rotation_mode = "XYZ"

    def eval_coords():
        deps = bpy.context.evaluated_depsgraph_get()
        return [v.co.copy() for v in mesh.evaluated_get(deps).data.vertices]

    def tail_z(sign):
        pb.rotation_euler = (sign * angle, 0.0, 0.0)
        bpy.context.view_layer.update()
        return (arm.matrix_world @ pb.tail).z

    sign = 1.0 if tail_z(1.0) < tail_z(-1.0) else -1.0
    pb.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    rest = eval_coords()
    pb.rotation_euler = (sign * angle, 0.0, 0.0)
    bpy.context.view_layer.update()
    posed = eval_coords()
    pb.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = mesh
    for m, show in saved:
        m.show_viewport = show

    if not (len(rest) == len(posed) == len(basis.data)):
        return (0.0, 0)
    sk = mesh.shape_key_add(name=sk_name, from_mix=False)  # starts equal to Basis
    sk.value = 0.0
    disp = 0.0
    for i in range(len(sk.data)):
        d = posed[i] - rest[i]
        sk.data[i].co = basis.data[i].co + d
        if d.length > disp:
            disp = d.length
    return (round(disp, 4), 1)


def _add_morph(obj, name, specs):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    sk = obj.shape_key_add(name=name, from_mix=False)
    max_disp = 0.0
    for group, direction, scale in specs:
        w = _group_weights(obj, group)
        d = mathutils.Vector(direction)
        if d.length > 0:
            d = d.normalized()
        for vi, weight in w.items():
            delta = d * (weight * scale)
            sk.data[vi].co = sk.data[vi].co + delta
            max_disp = max(max_disp, delta.length)
    return round(max_disp, 4), sum(len(_group_weights(obj, g)) for g, _, _ in specs)


def main():
    out_dir = _args()
    os.makedirs(out_dir, exist_ok=True)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    export_vrm = importlib.import_module("vrm_export").export_vrm

    bpy.ops.preferences.addon_enable(module="bl_ext.user_default.mpfb")
    HumanService = dynamic_import("mpfb.services.humanservice", "HumanService")
    ExportService = dynamic_import("mpfb.services.exportservice", "ExportService")

    basemesh = HumanService.create_human()
    arm = HumanService.add_builtin_rig(basemesh, "default")

    # Bake off the clothes-fitting helper shell -> clean ~13.4k head+body (WI 927), keep deform weights.
    ExportService.bake_modifiers_remove_helpers(
        basemesh, bake_masks=True, bake_subdiv=False, remove_helpers=True, also_proxy=True)
    bpy.context.view_layer.update()

    morph_report = {}
    # jawOpen: baked from a jaw BONE pose (skinning carries the lips open).
    disp, nk = _bake_bone_shapekey(basemesh, arm, "jawOpen", "jaw", angle=0.5)
    morph_report["jawOpen"] = {"max_disp_m": disp, "technique": "bone_pose_bake"}
    # blink + smile: weight-mask displacements (localized, single-group).
    specs = _morph_specs(basemesh)
    for name, spec in specs.items():
        disp, nverts = _add_morph(basemesh, name, spec)
        morph_report[name] = {"max_disp_m": disp, "masked_verts": nverts, "technique": "weight_mask"}

    authored = ["jawOpen", *specs.keys()]
    # Expression spec for vrm_export: 5 customs 1:1 + composed presets.
    expr = {
        "customs": {n: [(basemesh.name, n)] for n in authored},
        "presets": {
            "blink": [(basemesh.name, "eyeBlinkLeft"), (basemesh.name, "eyeBlinkRight")],
            "happy": [(basemesh.name, "mouthSmileLeft"), (basemesh.name, "mouthSmileRight")],
            "aa": [(basemesh.name, "jawOpen")],
        },
    }

    evidence = {
        "mesh": basemesh.name, "armature": arm.name,
        "clean_vertices": len(basemesh.data.vertices),
        "clean_polys": len(basemesh.data.polygons),
        "shape_keys": [k.name for k in basemesh.data.shape_keys.key_blocks],
        "morphs": morph_report,
    }
    with open(os.path.join(out_dir, "realistic_head_evidence.json"), "w") as fh:
        json.dump(evidence, fh, indent=2)
    print("EVIDENCE " + json.dumps(evidence))

    _render_heads(basemesh, out_dir, ["", *authored])

    # Purge scaffolding before export so the artifacts contain ONLY the avatar. This matters because the VRM
    # exporter sweeps the whole scene (it does not honor selection like glTF does), so Blender's default
    # startup Cube/Camera/Light, the render camera/light/aim empty, and MPFB bone-widget meshes would
    # otherwise ride along as stray objects (WI 938 owner review: a stray "Cube" appeared in the inspector).
    keep = {basemesh.name, arm.name}
    for o in list(bpy.data.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)

    # game-lane glb
    glb = os.path.join(out_dir, "realistic_head.glb")
    for o in bpy.context.scene.objects:
        o.select_set(False)
    basemesh.select_set(True); arm.select_set(True)
    bpy.context.view_layer.objects.active = basemesh
    bpy.ops.export_scene.gltf(filepath=glb, use_selection=True, export_format="GLB")

    p1, p0 = export_vrm(
        arm, out_dir, "realistic_head", author="asset-harness (WI 938 spike)",
        humanoid=HUMANOID_MPFB_DEFAULT, expressions=expr)
    print(f"WROTE {p1} {p0} {glb}")


def _render_heads(obj, out_dir, morph_names):
    """Head-framed front previews (camera on +Y): neutral + each morph at value 1.0."""
    scene = bpy.context.scene
    cam_d = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cam_d)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -0.62, 1.54)
    aim = bpy.data.objects.new("aim", None); aim.location = (0.0, 0.0, 1.55)
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO"); con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"
    scene.camera = cam
    cam_d.lens = 50
    ld = bpy.data.lights.new("k", type="SUN"); ld.energy = 3.5
    L = bpy.data.objects.new("k", ld); L.rotation_euler = (1.0, 0.1, -0.5)
    scene.collection.objects.link(L)
    engs = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engs else "BLENDER_EEVEE"
    scene.render.resolution_x = 480; scene.render.resolution_y = 560

    keys = obj.data.shape_keys.key_blocks if obj.data.shape_keys else {}
    for name in morph_names:
        for k in keys:
            if k.name != "Basis":
                k.value = 0.0
        label = name if name else "neutral"
        if name and name in keys:
            keys[name].value = 1.0
        scene.render.filepath = os.path.join(out_dir, f"rhead_{label}.png")
        bpy.context.view_layer.update()
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
