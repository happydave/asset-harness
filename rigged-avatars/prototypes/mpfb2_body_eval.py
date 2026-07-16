"""WI 927 — MPFB2 CC0 body-donor evaluation harness (headless).

Timeboxed evaluation, NOT a shipping generator. Answers one narrow empirical question:
does MPFB2's scripted path produce a skinned humanoid body whose topology + rig are worth
adopting over authoring the body parametrically from primitives (the WI 882/885 path)?

MPFB2 is a Blender 4.2 *extension*, so its modules live at an unknown place in the module
hierarchy — hence the `dynamic_import` quirk lifted verbatim from MPFB2's own script_samples.
Only the BUNDLED base mesh + built-in rigs are used (both CC0); no makehuman_system_assets
pack is required for a body-donor assessment (skins/clothes/eyes would need it).

Run (on ai2, after the extension is installed + enabled):
    ~/blender-4.2/blender --background --python mpfb2_body_eval.py -- \
        --rig default --out ~/mpfb-eval/out

Emits, per rig:
    <out>/mpfb_body_<rig>.blend      full scene (mesh + armature) for inspection
    <out>/mpfb_body_<rig>.glb        game-lane round-trip artifact
    <out>/mpfb_body_<rig>.png        front preview render (camera on +Y, faces the front)
    <out>/mpfb_body_<rig>.json       hard evidence: topology counts, bbox, bones, vgroups

The JSON is the evaluation's primary evidence; the render makes the aesthetic visible rather
than asserted.
"""

import importlib
import sys
import os
import json


def dynamic_import(absolute_package_str, key):
    """MPFB2 extension-import quirk (from MPFB2 script_samples/01)."""
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            mod = importlib.import_module(amod)
            if not hasattr(mod, key):
                raise AttributeError(f"Module {amod} lacks attribute {key}")
            return getattr(mod, key)
    raise ValueError(f"No module found ending in {absolute_package_str}")


def _argv_after_ddash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _parse_args(argv):
    rig, out = "default", os.path.expanduser("~/mpfb-eval/out")
    i = 0
    while i < len(argv):
        if argv[i] == "--rig":
            rig = argv[i + 1]; i += 2
        elif argv[i] == "--out":
            out = os.path.expanduser(argv[i + 1]); i += 2
        else:
            i += 1
    return rig, out


# Our target: the 19-bone VRM humanoid contract the track already exports to (WI 925).
# Names here are the VRM humanoid bone slots; the comparison is by anatomical slot, not by
# MPFB's literal bone strings (those differ per rig — that IS part of what we're assessing).
VRM_HUMANOID_SLOTS = [
    "hips", "spine", "chest", "neck", "head",
    "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    "leftUpperLeg", "leftLowerLeg", "leftFoot",
    "rightUpperLeg", "rightLowerLeg", "rightFoot",
]


def main():
    import bpy

    rig_name, out_dir = _parse_args(_argv_after_ddash())
    os.makedirs(out_dir, exist_ok=True)

    # Enable the MPFB extension in this headless session (idempotent).
    try:
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.mpfb")
    except Exception as exc:  # noqa: BLE001 - report, don't crash the eval
        print(f"[warn] addon_enable raised: {exc}")

    HumanService = dynamic_import("mpfb.services.humanservice", "HumanService")

    # 1. Bundled CC0 base mesh.
    basemesh = HumanService.create_human()

    # 2. Bundled CC0 built-in rig (skinned: import_weights defaults True).
    armature = HumanService.add_builtin_rig(basemesh, rig_name)

    bpy.context.view_layer.update()

    # --- Evidence gathering -------------------------------------------------
    mesh = basemesh.data
    tri = quad = ngon = 0
    for poly in mesh.polygons:
        n = len(poly.vertices)
        if n == 3:
            tri += 1
        elif n == 4:
            quad += 1
        else:
            ngon += 1

    # World-space bounding box (height/width/depth in metres).
    import mathutils
    coords = [basemesh.matrix_world @ mathutils.Vector(c) for c in basemesh.bound_box]
    xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
    dims = {
        "width_x": round(max(xs) - min(xs), 4),
        "depth_y": round(max(ys) - min(ys), 4),
        "height_z": round(max(zs) - min(zs), 4),
    }

    bones = [b.name for b in armature.data.bones] if armature and armature.type == "ARMATURE" else []
    deform_bones = [b.name for b in armature.data.bones if b.use_deform] if bones else []
    vgroups = [g.name for g in basemesh.vertex_groups]

    # Naive slot coverage: does a bone name contain the anatomical token? (case-insensitive)
    lowered = [b.lower() for b in bones]
    slot_hits = {}
    slot_tokens = {
        "hips": ["pelvis", "hip", "root"], "spine": ["spine"], "chest": ["chest", "spine02", "spine03"],
        "neck": ["neck"], "head": ["head"],
        "leftShoulder": ["clavicle.l", "shoulder.l", "clavicle_l", "shoulder_l"],
        "leftUpperArm": ["upperarm.l", "upper_arm.l", "shoulder01.l", "upperarm_l"],
        "leftLowerArm": ["lowerarm.l", "forearm.l", "lowerarm_l"],
        "leftHand": ["hand.l", "wrist.l", "hand_l"],
        "rightShoulder": ["clavicle.r", "shoulder.r", "clavicle_r"],
        "rightUpperArm": ["upperarm.r", "upper_arm.r", "upperarm_r"],
        "rightLowerArm": ["lowerarm.r", "forearm.r", "lowerarm_r"],
        "rightHand": ["hand.r", "wrist.r", "hand_r"],
        "leftUpperLeg": ["upperleg.l", "thigh.l", "upper_leg.l", "upperleg_l"],
        "leftLowerLeg": ["lowerleg.l", "shin.l", "calf.l", "lowerleg_l"],
        "leftFoot": ["foot.l", "foot_l"],
        "rightUpperLeg": ["upperleg.r", "thigh.r", "upperleg_r"],
        "rightLowerLeg": ["lowerleg.r", "shin.r", "calf.r"],
        "rightFoot": ["foot.r", "foot_r"],
    }
    for slot in VRM_HUMANOID_SLOTS:
        toks = slot_tokens.get(slot, [slot.lower()])
        slot_hits[slot] = any(any(t in bn for t in toks) for bn in lowered)

    evidence = {
        "rig": rig_name,
        "mesh_object": basemesh.name,
        "armature_object": armature.name if armature else None,
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
        "tris": tri, "quads": quad, "ngons": ngon,
        "quad_fraction": round(quad / max(len(mesh.polygons), 1), 4),
        "materials": [m.name for m in mesh.materials],
        "dimensions_m": dims,
        "bone_count": len(bones),
        "deform_bone_count": len(deform_bones),
        "bones": bones,
        "vertex_group_count": len(vgroups),
        "vrm_slot_coverage": slot_hits,
        "vrm_slots_covered": sum(1 for v in slot_hits.values() if v),
        "vrm_slots_total": len(VRM_HUMANOID_SLOTS),
    }
    json_path = os.path.join(out_dir, f"mpfb_body_{rig_name}.json")
    with open(json_path, "w") as fh:
        json.dump(evidence, fh, indent=2)
    print("EVIDENCE " + json.dumps(evidence))

    # --- Persist artifacts --------------------------------------------------
    blend_path = os.path.join(out_dir, f"mpfb_body_{rig_name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    glb_path = os.path.join(out_dir, f"mpfb_body_{rig_name}.glb")
    bpy.ops.object.select_all(action="DESELECT")
    basemesh.select_set(True)
    if armature:
        armature.select_set(True)
    bpy.context.view_layer.objects.active = basemesh
    bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format="GLB")

    _render_front(bpy, basemesh, os.path.join(out_dir, f"mpfb_body_{rig_name}.png"))
    print(f"WROTE {blend_path} {glb_path} {json_path}")


def _render_front(bpy, subject, png_path):
    """Front preview: camera on +Y (character front), TRACK_TO the subject. The corn/head
    generators established +Y is the face-forward axis; a -Y camera photographs the back."""
    import mathutils
    scene = bpy.context.scene

    cam_data = bpy.data.cameras.new("eval_cam")
    cam = bpy.data.objects.new("eval_cam", cam_data)
    scene.collection.objects.link(cam)
    # Frame the ~1.8 m figure from the front, slightly above waist height.
    cam.location = (0.0, -3.6, 1.0)
    con = cam.constraints.new("TRACK_TO")
    con.target = subject
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    light_data = bpy.data.lights.new("eval_key", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("eval_key", light_data)
    light.rotation_euler = (mathutils.Euler((1.1, 0.0, -0.5))).to_quaternion().to_euler()
    scene.collection.objects.link(light)

    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in \
        {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 900
    scene.render.filepath = png_path
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
