#!/usr/bin/env python3
"""Prototype A (WI 882): a rigged, rigid-humanoid "robot" avatar — the Direction-A pipeline with
NO AI in the loop. Runs in Blender headless on `ai2`:

    blender --background --python blender_robot.py -- --out DIR

Pipeline (discover.md Direction A + the research findings it enforces):
  1. Parametric geometry — bpy primitives (boxes/cylinders), authored by hand. No image-to-3D.
  2. A standard humanoid ARMATURE (hips→spine→chest→neck→head; shoulder→upper_arm→forearm→hand;
     thigh→shin→foot, both sides).
  3. RIGID bind: each rigid part is object-parented to exactly ONE bone (Blender `Ctrl+P → Bone`).
     No vertex weights, no skinning, zero deformation by construction. On glTF export this becomes a
     plain node hierarchy: each part a node under its joint node, TRS-animated.
  4. Hand-keyed motion (idle + walk) — authored, not sourced from any mocap / text-to-motion corpus
     (those are non-commercially licensed; see discover.md). So the motion data is ours and clean.

Authoring frame: Blender-native **Z-up** (character stands along +Z, faces +Y, +X is its left).
The default glTF exporter's +Y-up conversion yields the engine contract: **+Y up, metres**.

Outputs under <out>/:
  robot.glb              — GLB with the full part hierarchy + armature + `idle` and `walk` clips
  debug/robot.gltf(+bin) — separate-file variant (easier to inspect/debug; research advice)
  robot_manifest.json    — bones, parts→bone map, clips, provenance

License: fully clean — Blender (GPL tool; outputs are yours) + authored geometry + hand-keyed motion.
"""
import bpy, sys, json, math, os
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/robot")
OUT.mkdir(parents=True, exist_ok=True)
FPS = 24

# ---- materials -------------------------------------------------------------
def mat(name, rgb, metallic, rough, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if emit and "Emission Color" in b.inputs:
        b.inputs["Emission Color"].default_value = (*rgb, 1.0)
        b.inputs["Emission Strength"].default_value = emit
    return m

def M_body():   return mat("body",   (0.60, 0.62, 0.66), 1.0, 0.40)
def M_dark():   return mat("dark",   (0.28, 0.30, 0.34), 1.0, 0.50)
def M_accent(): return mat("accent", (0.10, 0.72, 0.82), 0.3, 0.20, emit=1.5)

def assign(o, m):
    o.data.materials.clear(); o.data.materials.append(m)

# ---- primitives (authored at world position; Z-up) -------------------------
def box(name, sx, sy, sz, loc, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object; o.name = name
    o.scale = (sx / 2, sy / 2, sz / 2)
    bpy.ops.object.transform_apply(scale=True)          # apply scale before export
    assign(o, m); return o

def cyl(name, r, h, loc, m):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=20)
    o = bpy.context.active_object; o.name = name; assign(o, m); return o

def sphere(name, r, loc, m):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=16, ring_count=8)
    o = bpy.context.active_object; o.name = name; assign(o, m); return o

# ---- armature --------------------------------------------------------------
# (name, head, tail, parent). Limb bones point downward (arms/legs hang); leg/arm swing is a
# rotation about the bone-local X axis, which for these near-vertical bones ~= world X (sagittal).
def bone_defs():
    B = [
        ("hips",  (0, 0, 0.92), (0, 0, 1.05), None),
        ("spine", (0, 0, 1.05), (0, 0, 1.25), "hips"),
        ("chest", (0, 0, 1.25), (0, 0, 1.45), "spine"),
        ("neck",  (0, 0, 1.45), (0, 0, 1.55), "chest"),
        ("head",  (0, 0, 1.55), (0, 0, 1.80), "neck"),
    ]
    for s, suf in ((1, "L"), (-1, "R")):
        B += [
            (f"shoulder.{suf}",  (0.05 * s, 0, 1.45), (0.22 * s, 0, 1.45), "chest"),
            (f"upper_arm.{suf}", (0.22 * s, 0, 1.45), (0.22 * s, 0, 1.15), f"shoulder.{suf}"),
            (f"forearm.{suf}",   (0.22 * s, 0, 1.15), (0.22 * s, 0, 0.90), f"upper_arm.{suf}"),
            (f"hand.{suf}",      (0.22 * s, 0, 0.90), (0.22 * s, 0, 0.78), f"forearm.{suf}"),
            (f"thigh.{suf}",     (0.11 * s, 0, 0.92), (0.11 * s, 0, 0.50), "hips"),
            (f"shin.{suf}",      (0.11 * s, 0, 0.50), (0.11 * s, 0, 0.09), f"thigh.{suf}"),
            (f"foot.{suf}",      (0.11 * s, 0, 0.09), (0.11 * s, 0.20, 0.04), f"shin.{suf}"),
        ]
    return B

def build_armature():
    arm_data = bpy.data.armatures.new("robot_arm")
    arm = bpy.data.objects.new("robot_rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones
    for name, head, tail, parent in bone_defs():
        b = eb.new(name); b.head = head; b.tail = tail; b.use_connect = False
        if parent:
            b.parent = eb[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm

# ---- rigid bone-parent (preserves world transform; no jump, no deform) -----
def parent_to_bone(obj, arm, bone_name):
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = 'BONE'
    obj.parent_bone = bone_name
    bpy.context.view_layer.update()
    obj.matrix_world = world                             # recompute local so it stays put

# ---- parts (name, bone, builder) -------------------------------------------
def build_parts(arm):
    body, dark, accent = M_body(), M_dark(), M_accent()
    parts = []  # (obj, bone)
    # centre column
    parts.append((box("pelvis", 0.30, 0.20, 0.16, (0, 0, 0.95), body), "hips"))
    parts.append((box("torso",  0.36, 0.24, 0.34, (0, 0, 1.28), body), "chest"))
    parts.append((cyl("neck_m", 0.05, 0.10, (0, 0, 1.50), dark), "neck"))
    parts.append((box("head_m", 0.26, 0.26, 0.26, (0, 0, 1.66), body), "head"))
    parts.append((box("eye.L", 0.05, 0.03, 0.05, (0.06, 0.13, 1.69), accent), "head"))
    parts.append((box("eye.R", 0.05, 0.03, 0.05, (-0.06, 0.13, 1.69), accent), "head"))
    parts.append((cyl("antenna", 0.012, 0.14, (0, 0, 1.87), dark), "head"))
    parts.append((sphere("antenna_tip", 0.03, (0, 0, 1.95), accent), "head"))
    # limbs (both sides)
    for s, suf in ((1, "L"), (-1, "R")):
        parts.append((box(f"shoulder_m.{suf}", 0.14, 0.16, 0.16, (0.16 * s, 0, 1.45), dark), f"shoulder.{suf}"))
        parts.append((cyl(f"upper_arm_m.{suf}", 0.050, 0.30, (0.22 * s, 0, 1.30), dark), f"upper_arm.{suf}"))
        parts.append((cyl(f"forearm_m.{suf}", 0.042, 0.25, (0.22 * s, 0, 1.025), dark), f"forearm.{suf}"))
        parts.append((box(f"hand_m.{suf}", 0.08, 0.07, 0.13, (0.22 * s, 0, 0.83), body), f"hand.{suf}"))
        parts.append((cyl(f"thigh_m.{suf}", 0.065, 0.42, (0.11 * s, 0, 0.71), dark), f"thigh.{suf}"))
        parts.append((cyl(f"shin_m.{suf}", 0.055, 0.41, (0.11 * s, 0, 0.295), dark), f"shin.{suf}"))
        parts.append((box(f"foot_m.{suf}", 0.13, 0.26, 0.09, (0.11 * s, 0.05, 0.05), body), f"foot.{suf}"))
    for obj, bone in parts:
        parent_to_bone(obj, arm, bone)
    return [(o.name, b) for o, b in parts]

# ---- animation -------------------------------------------------------------
# keys: { bone: { channel: [(frame, value), ...] } }, channel in {rot_x, rot_y, loc_y}
def make_action(name, arm, keys):
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True                              # keep it so ACTIONS export sees it
    arm.animation_data.action = act
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:                             # neutral baseline
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (0, 0, 0); pb.location = (0, 0, 0)
    idx = {"rot_x": ("rotation_euler", 0), "rot_y": ("rotation_euler", 1),
           "rot_z": ("rotation_euler", 2), "loc_y": ("location", 1)}
    for bone, chans in keys.items():
        pb = arm.pose.bones[bone]
        for chan, kfs in chans.items():
            prop, i = idx[chan]
            for f, v in kfs:
                getattr(pb, prop)[i] = v
                pb.keyframe_insert(prop, index=i, frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    return act

def walk_keys():
    T, A = 0.45, 0.35   # thigh / arm swing amplitude (rad); cycle = 24 frames (key 1,7,13,19,25)
    return {
        "thigh.L":     {"rot_x": [(1, +T), (7, 0), (13, -T), (19, 0), (25, +T)]},
        "thigh.R":     {"rot_x": [(1, -T), (7, 0), (13, +T), (19, 0), (25, -T)]},
        # shin rotates NEGATIVE so the calf tucks backward (human knee, not a reverse/bird knee)
        "shin.L":      {"rot_x": [(1, -0.20), (7, -0.30), (13, -0.25), (19, -0.95), (25, -0.20)]},
        "shin.R":      {"rot_x": [(1, -0.95), (7, -0.25), (13, -0.20), (19, -0.30), (25, -0.95)]},
        "upper_arm.L": {"rot_x": [(1, -A), (7, 0), (13, +A), (19, 0), (25, -A)]},
        "upper_arm.R": {"rot_x": [(1, +A), (7, 0), (13, -A), (19, 0), (25, +A)]},
        "forearm.L":   {"rot_x": [(1, 0.20), (13, 0.35), (25, 0.20)]},
        "forearm.R":   {"rot_x": [(1, 0.35), (13, 0.20), (25, 0.35)]},
        "spine":       {"rot_x": [(1, 0.10)]},                            # slight forward lean (dynamism)
        "chest":       {"rot_y": [(1, 0.08), (13, -0.08), (25, 0.08)]},   # subtle torso twist
        "hips":        {"loc_y": [(1, 0.0), (7, 0.03), (13, 0.0), (19, 0.03), (25, 0.0)]},  # bob (local Y=up)
    }

def idle_keys():
    return {
        "hips":        {"loc_y": [(1, 0.0), (24, 0.012), (48, 0.0)]},
        "upper_arm.L": {"rot_x": [(1, 0.0), (24, 0.04), (48, 0.0)]},
        "upper_arm.R": {"rot_x": [(1, 0.0), (24, -0.04), (48, 0.0)]},
        "head":        {"rot_y": [(1, 0.0), (24, 0.05), (48, 0.0)]},
    }

# ---- clip metadata (authoritative source; → sidecar + baked into glb extras) ----
# Foot schedule for the walk (50% duty: each foot planted half the cycle). Derived from the
# walk_keys phasing — L leads (thigh.L is forward at the frame-1 contact). These frames are what a
# downstream procedural-IK gait would lock the foot to the ground at (and release).
# Events are located by `frame` + normalized `phase` (0..1 across the clip). Phase is
# convention-independent; the baker converts it to an exact `timeSec` on the glb's own time axis
# (Blender exports keyframe times as frame/fps, so absolute seconds must come from the glb, not fps).
def clip_meta():
    def ph(f, start, end):
        return round((f - start) / (end - start), 5)
    ws, we = 1, 25
    walk_events = [
        {"frame": 1,  "phase": ph(1,  ws, we), "type": "foot_plant", "foot": "L"},
        {"frame": 13, "phase": ph(13, ws, we), "type": "foot_lift",  "foot": "L"},
        {"frame": 13, "phase": ph(13, ws, we), "type": "foot_plant", "foot": "R"},
        {"frame": 25, "phase": ph(25, ws, we), "type": "foot_lift",  "foot": "R"},
    ]
    return {
        "walk": {"loop": True, "fps": FPS, "frame_start": ws, "frame_end": we,
                 "nominal_duration_s": round((we - ws) / FPS, 4), "events": walk_events},
        "idle": {"loop": True, "fps": FPS, "frame_start": 1, "frame_end": 48,
                 "nominal_duration_s": round(47 / FPS, 4), "events": []},
    }

# ---- export ----------------------------------------------------------------
def export(arm):
    bpy.ops.object.select_all(action='SELECT')
    common = dict(export_animations=True, export_animation_mode='ACTIONS', use_selection=True)
    bpy.ops.export_scene.gltf(filepath=str(OUT / "robot.glb"), export_format='GLB', **common)
    dbg = OUT / "debug"; dbg.mkdir(exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(dbg / "robot.gltf"), export_format='GLTF_SEPARATE', **common)

# ---- main ------------------------------------------------------------------
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = build_armature()
    parts = build_parts(arm)
    make_action("walk", arm, walk_keys())
    idle = make_action("idle", arm, idle_keys())
    arm.animation_data.action = bpy.data.actions["walk"]  # leave walk active for preview
    _ = idle
    export(arm)
    manifest = {
        "asset": "rigged rigid-humanoid robot (Direction A)",
        "frame": "authored Z-up; exported +Y up, metres (glTF default conversion)",
        "bind": "rigid: each part object-parented to one bone; no skin weights, no deformation",
        "clips": clip_meta(),
        "bones": [b[0] for b in bone_defs()],
        "parts": {name: bone for name, bone in parts},
        "license": "clean: Blender (GPL) + authored geometry + hand-keyed motion",
    }
    (OUT / "robot_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"built robot: {len(parts)} parts, {len(bone_defs())} bones -> {OUT/'robot.glb'}")

if __name__ == "__main__":
    main()
