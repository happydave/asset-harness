#!/usr/bin/env python3
"""WI 926 SPIKE (kill-shot): does a **skinned mesh carrying real shape keys** survive headless
Blender -> VRM (1.0 + 0.x) with skin + morphs intact, ARKit-named, and drivable in a consumer?

    ~/blender-4.2/blender --background --python blender_face_spike.py -- --out DIR

The repo has ZERO skin weights and ZERO shape keys today (every existing avatar is rigidly
bone-parented). This is the first time the skinned + morph path is walked at all. It is deliberately
small but **representative**: skinning is tested WITH shape keys present, in one mesh, in one export
(not skinning in isolation) — the workspace has been bitten twice by reduced fixtures masking failures.

Emits, from one run:
  face_spike.glb       — game-lane glTF: skinned mesh + 4 morph targets + one bone "nod" clip.
  face_spike.vrm       — VRM 1.0 (master): humanoid + skin + morphs + ARKit expressions.
  face_spike.vrm0.vrm  — VRM 0.x (derived, VSeeFace): humanoid + skin + morphs + preset blend shapes.
  face_spike_manifest.json — provenance.

Four ARKit-named shape keys (exact camelCase, from day one): eyeBlinkLeft, eyeBlinkRight, jawOpen,
mouthSmileLeft. Bound as 1:1 VRM customs AND composed into presets (blink / aa / happy) — the research
"one morph per clip, compose in presets" rule, and the file that answers Warudo binding precedence.

Requires Blender 4.2+ with the saturday06 VRM add-on (on ai2: ~/blender-4.2/blender). Clean licence:
authored geometry + hand-set morphs; the add-on's GPL/MIT imposes nothing on the output.
"""
import bpy, sys, json
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/face_spike")
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_corn import corn_bone_defs, build_armature, make_action  # pure helpers; identical bone names
import vrm_export

HEAD_MESH = "face_head"
BODY_MESH = "face_body"
# four real ARKit morphs (blink x2, jaw, one emotion) — exact ARKit camelCase.
ARKIT_KEYS = ["eyeBlinkLeft", "eyeBlinkRight", "jawOpen", "mouthSmileLeft"]


def _mat(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    return m


def _sphere(name, r, loc, seg, ring, m):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=seg, ring_count=ring)
    o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)  # verts in world/armature space
    o.data.materials.clear(); o.data.materials.append(m)
    return o


def _disp(co, key):
    """Per-shape-key vertex displacement in armature space (Z-up). Front = +Y. Head centred ~z1.13.
    Each key deforms a DISTINCT region so the four morphs are visibly separable."""
    x, y, z = co
    front = y > 0.06
    if key == "eyeBlinkLeft" and front and 1.15 <= z <= 1.24 and 0.03 <= x <= 0.11:
        return (0.0, 0.0, -0.035)                       # left eyelid drops
    if key == "eyeBlinkRight" and front and 1.15 <= z <= 1.24 and -0.11 <= x <= -0.03:
        return (0.0, 0.0, -0.035)                       # right eyelid drops
    if key == "jawOpen" and y > 0.03 and 0.97 <= z <= 1.08:
        return (0.0, 0.02, -0.06)                       # jaw/chin drops + juts
    if key == "mouthSmileLeft" and front and 1.01 <= z <= 1.10 and x > 0.0:
        return (0.02, 0.0, 0.03)                        # left mouth corner lifts + widens
    return (0.0, 0.0, 0.0)


def add_shape_keys(obj):
    obj.shape_key_add(name="Basis", from_mix=False)
    for key in ARKIT_KEYS:
        sk = obj.shape_key_add(name=key, from_mix=False)     # copies Basis
        for i, v in enumerate(obj.data.vertices):
            bx, by, bz = v.co
            dx, dy, dz = _disp((bx, by, bz), key)
            sk.data[i].co = (bx + dx, by + dy, bz + dz)
        sk.value = 0.0
    return list(ARKIT_KEYS)


def skin(meshes, arm):
    """Real skinning: ARMATURE_AUTO generates vertex groups + an armature modifier (NOT bone-parenting)."""
    bpy.ops.object.select_all(action='DESELECT')
    for mo in meshes:
        mo.select_set(True)
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')


def manifest():
    return {
        "asset": "WI 926 skinned + shape-key VRM spike (kill-shot probe)",
        "generator_script": "blender_face_spike.py",
        "frame": "authored Z-up; exported +Y up, metres",
        "bind": "SKINNED: armature modifier + auto vertex weights (NOT object/bone-parenting)",
        "meshes": [HEAD_MESH, BODY_MESH],
        "shape_keys_arkit": ARKIT_KEYS,
        "expression_binding": "1:1 VRM1 customs (raw ARKit) + composed presets blink/aa/happy; VRM0 preset groups",
        "clip": {"nod": {"loop": False, "fps": 24, "frame_start": 1, "frame_end": 24}},
        "artifacts": ["face_spike.glb", "face_spike.vrm", "face_spike.vrm0.vrm"],
        "license": "clean: Blender (GPL) + authored geometry + hand-set morphs",
    }


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)     # NB: disables the VRM add-on; export re-enables it
    arm = build_armature(corn_bone_defs(), "spike")

    skin_mat = _mat("skin", (0.86, 0.72, 0.60))
    body_mat = _mat("body", (0.35, 0.45, 0.70))
    head = _sphere(HEAD_MESH, 0.16, (0, 0, 1.13), 24, 16, skin_mat)     # dense enough for regional morphs
    body = _sphere(BODY_MESH, 0.20, (0, 0, 0.72), 16, 10, body_mat)
    body.scale = (1.0, 0.7, 1.9); bpy.ops.object.transform_apply(scale=True)

    keys = add_shape_keys(head)                           # 4 ARKit morphs on the head mesh only
    skin([head, body], arm)                               # real armature-modifier skinning

    # one bone "nod" clip so the .glb carries an animation (tests skin-deform-under-bone + the clip question)
    make_action("nod", arm, {"head": {"rot_x": [(1, 0.0), (12, 0.45), (24, 0.0)]}})
    arm.animation_data.action = bpy.data.actions["nod"]

    # game-lane glb: skin + morphs + clip
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(OUT / "face_spike.glb"), export_format='GLB',
                              export_animations=True, export_animation_mode='ACTIONS',
                              export_morph=True, use_selection=True)

    # expression spec: raw ARKit as 1:1 customs; double-duty shapes composed into presets
    expr = {
        "customs": {k: [(HEAD_MESH, k)] for k in keys},
        "presets": {
            "blink": [(HEAD_MESH, "eyeBlinkLeft"), (HEAD_MESH, "eyeBlinkRight")],
            "aa":    [(HEAD_MESH, "jawOpen")],
            "happy": [(HEAD_MESH, "mouthSmileLeft")],
        },
    }
    p1, p0 = vrm_export.export_vrm(arm, OUT, "face_spike", author="asset-harness (WI 926)", expressions=expr)
    (OUT / "face_spike_manifest.json").write_text(json.dumps(manifest(), indent=2))
    print(f"built skinned+shapekey spike: {OUT/'face_spike.glb'}, {p1}, {p0}")


if __name__ == "__main__":
    main()
