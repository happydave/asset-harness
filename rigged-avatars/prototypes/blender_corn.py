#!/usr/bin/env python3
"""Prototype B (WI 885): a Kerbal-tier stylized **corn-cob person** + its **corn -> popcorn**
failure-state asset. Blender headless on `ai2`, no AI in the loop:

    blender --background --python blender_corn.py -- --out DIR

Builds two linked assets (the discovery's "failure transform = a swap, not a deform"):
  corn.glb          — rigged Kerbal-tier corn person (armature + rigid bone-parented parts + idle/walk).
                      Reuses the Prototype-A rig + walk keys verbatim (the rig generalizes).
  popcorn_burst.glb — the failure state: a seeded scatter of popcorn puffs with a one-shot `pop` clip
                      (object-animated, exported via glTF SCENE mode). The engine despawns the avatar
                      and spawns this on a catastrophic-failure event.

Authoring frame Z-up; exported +Y up, metres. License: clean (Blender GPL + authored geometry +
hand-keyed motion). Extras + the corn->popcorn link are baked by `bake_glb_extras.py`.
"""
import bpy, sys, json, math, random
from pathlib import Path
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/corn")
OUT.mkdir(parents=True, exist_ok=True)
FPS = 24
# `--heads a,b,c` builds only those corn head variants (corn_<v>.glb), no popcorn — for comparison.
HEADS = argv[argv.index("--heads") + 1].split(",") if "--heads" in argv else None
# `--vrm` also emits corn.vrm (1.0) + corn.vrm0.vrm (0.x) via the saturday06 VRM add-on (WI 925).
# Requires a Blender 4.2+ with that add-on (on ai2: ~/blender-4.2/blender). Adds a husk-tuft spring chain.
VRM = "--vrm" in argv

# ---- shared helpers (same idioms as blender_robot.py) ----------------------
def mat(name, rgb, metallic, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    return m

def M_corn():    return mat("corn_yellow", (0.95, 0.80, 0.15), 0.0, 0.50)
def M_husk():    return mat("husk_green",  (0.30, 0.52, 0.18), 0.0, 0.60)
def M_cream():   return mat("cream",       (0.98, 0.93, 0.72), 0.0, 0.50)
def M_eye():     return mat("eye_dark",    (0.08, 0.08, 0.10), 0.0, 0.30)
def M_pop():     return mat("popcorn",     (0.98, 0.95, 0.86), 0.0, 0.70)
def M_hair():    return mat("hair",        (0.34, 0.22, 0.11), 0.0, 0.70)

def assign(o, m):
    o.data.materials.clear(); o.data.materials.append(m)

def join(objs):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return bpy.context.active_object

def box(name, sx, sy, sz, loc, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object; o.name = name
    o.scale = (sx / 2, sy / 2, sz / 2); bpy.ops.object.transform_apply(scale=True)
    assign(o, m); return o

def cyl(name, r, h, loc, m):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=18)
    o = bpy.context.active_object; o.name = name; assign(o, m); return o

def lowsphere(r, loc):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=8, ring_count=4)
    return bpy.context.active_object

def cone(name, r1, r2, depth, loc, m, verts=16):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, location=loc, vertices=verts)
    o = bpy.context.active_object; o.name = name; assign(o, m); return o

def parent_to_bone(obj, arm, bone_name):
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = arm; obj.parent_type = 'BONE'; obj.parent_bone = bone_name
    bpy.context.view_layer.update()
    obj.matrix_world = world

def make_action(name, arm, keys):
    if arm.animation_data is None: arm.animation_data_create()
    act = bpy.data.actions.new(name); act.use_fake_user = True
    arm.animation_data.action = act
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'; pb.rotation_euler = (0, 0, 0); pb.location = (0, 0, 0)
    idx = {"rot_x": ("rotation_euler", 0), "rot_y": ("rotation_euler", 1),
           "rot_z": ("rotation_euler", 2), "loc_y": ("location", 1)}
    for bone, chans in keys.items():
        pb = arm.pose.bones[bone]
        for chan, kfs in chans.items():
            prop, i = idx[chan]
            for f, v in kfs:
                getattr(pb, prop)[i] = v; pb.keyframe_insert(prop, index=i, frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    return act

# ---- corn person: armature (Kerbal proportions: short, big head) -----------
def corn_bone_defs():
    B = [
        ("hips",  (0, 0, 0.55), (0, 0, 0.66), None),
        ("spine", (0, 0, 0.66), (0, 0, 0.85), "hips"),
        ("chest", (0, 0, 0.85), (0, 0, 0.95), "spine"),
        ("neck",  (0, 0, 0.95), (0, 0, 1.00), "chest"),
        ("head",  (0, 0, 1.00), (0, 0, 1.30), "neck"),
    ]
    for s, suf in ((1, "L"), (-1, "R")):
        B += [
            (f"shoulder.{suf}",  (0.05 * s, 0, 0.90), (0.16 * s, 0, 0.90), "chest"),
            (f"upper_arm.{suf}", (0.16 * s, 0, 0.90), (0.16 * s, 0, 0.72), f"shoulder.{suf}"),
            (f"forearm.{suf}",   (0.16 * s, 0, 0.72), (0.16 * s, 0, 0.58), f"upper_arm.{suf}"),
            (f"hand.{suf}",      (0.16 * s, 0, 0.58), (0.16 * s, 0, 0.50), f"forearm.{suf}"),
            (f"thigh.{suf}",     (0.09 * s, 0, 0.55), (0.09 * s, 0, 0.34), "hips"),
            (f"shin.{suf}",      (0.09 * s, 0, 0.34), (0.09 * s, 0, 0.09), f"thigh.{suf}"),
            (f"foot.{suf}",      (0.09 * s, 0, 0.09), (0.09 * s, 0.16, 0.03), f"shin.{suf}"),
        ]
    return B

def build_armature(defs, obj_name):
    ad = bpy.data.armatures.new(obj_name + "_arm")
    arm = bpy.data.objects.new(obj_name, ad)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm; arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = ad.edit_bones
    for name, head, tail, parent in defs:
        b = eb.new(name); b.head = head; b.tail = tail; b.use_connect = False
        if parent: b.parent = eb[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm

def build_cob(m_yellow):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.40, location=(0, 0, 0.75), vertices=20)
    body = bpy.context.active_object
    ker = []
    for ri, z in enumerate((0.60, 0.68, 0.76, 0.84, 0.90)):
        for c in range(8):
            a = math.radians(c * 45 + (22.5 if ri % 2 else 0))
            ker.append(lowsphere(0.024, (0.15 * math.cos(a), 0.15 * math.sin(a), z)))
    o = join([body] + ker); o.name = "cob"; assign(o, m_yellow); return o

# ---- head variants (all parented to the "head" bone; all carry a face) -----
def add_face(objs, eye, ez, ey=0.15, r=0.030, sw=0.11):
    def eyeball(x):
        o = lowsphere(r, (x, ey, ez + 0.03)); o.name = "eye"; assign(o, eye); return o
    objs += [eyeball(0.062), eyeball(-0.062),
             box("smile", sw, 0.02, 0.025, (0, ey + 0.005, ez - 0.07), eye)]

def build_head(variant, yellow, husk, cream, eye):
    """Return a list of head-part objects for `variant`. Head bone spans z 1.00..1.30."""
    objs = []
    if variant == "classic":                       # rounded cream dome (the original)
        h = lowsphere(0.17, (0, 0, 1.13)); h.name = "head_classic"; h.scale = (1, 1, 0.95)
        bpy.ops.object.transform_apply(scale=True); assign(h, cream); objs.append(h)
        add_face(objs, eye, 1.15, ey=0.15)
    elif variant == "human":                        # taller oval + nose + brown hair
        h = lowsphere(0.155, (0, 0, 1.15)); h.name = "head_human"; h.scale = (0.92, 1.0, 1.16)
        bpy.ops.object.transform_apply(scale=True); assign(h, cream); objs.append(h)
        nose = lowsphere(0.028, (0, 0.155, 1.13)); nose.name = "nose"; assign(nose, cream); objs.append(nose)
        hair = M_hair()
        for x in (-0.09, -0.03, 0.03, 0.09):
            s = box(f"hair_{x}", 0.035, 0.11, 0.05, (x, -0.05, 1.29), hair)
            s.rotation_euler = (math.radians(-28), 0, 0); bpy.ops.object.transform_apply(rotation=True)
            objs.append(s)
        add_face(objs, eye, 1.16, ey=0.145, r=0.025, sw=0.085)
    elif variant == "kernel":                       # head IS one big corn kernel (tooth shape)
        body = cone("kernel_body", 0.05, 0.17, 0.20, (0, 0, 1.10), yellow)
        cap = lowsphere(0.17, (0, 0, 1.20)); cap.scale = (1, 1, 0.62)
        bpy.ops.object.transform_apply(scale=True); assign(cap, yellow)
        o = join([body, cap]); o.name = "kernel_head"; assign(o, yellow); objs.append(o)
        add_face(objs, eye, 1.15, ey=0.145)
    elif variant == "cob":                          # head is a mini corn cob + husk tuft
        bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.24, location=(0, 0, 1.14), vertices=16)
        body = bpy.context.active_object
        ker = []
        for ri, z in enumerate((1.05, 1.12, 1.19)):
            for c in range(6):
                a = math.radians(c * 60 + (30 if ri % 2 else 0))
                ker.append(lowsphere(0.022, (0.12 * math.cos(a), 0.12 * math.sin(a), z)))
        o = join([body] + ker); o.name = "cob_head"; assign(o, yellow); objs.append(o)
        for c in range(3):                           # husk tuft sprouting from the top
            a = math.radians(c * 120 + 30)
            lf = cone(f"tuft_{c}", 0.04, 0.0, 0.16, (0.05 * math.cos(a), 0.05 * math.sin(a), 1.30), husk)
            axis = Vector((-math.sin(a), math.cos(a), 0))
            lf.rotation_euler = Matrix.Rotation(math.radians(20), 4, axis).to_euler()
            bpy.ops.object.transform_apply(rotation=True); objs.append(lf)
        add_face(objs, eye, 1.14, ey=0.115, r=0.026, sw=0.09)
    else:
        raise ValueError(f"unknown head variant: {variant}")
    return objs

def build_corn_parts(arm, head_variant="classic"):
    yellow, husk, cream, eye = M_corn(), M_husk(), M_cream(), M_eye()
    parts = []
    parts.append((box("pelvis", 0.16, 0.14, 0.10, (0, 0, 0.58), yellow), "hips"))
    parts.append((build_cob(yellow), "spine"))
    # husk leaves splaying up around the neck
    for c in range(3):
        a = math.radians(c * 120 + 30)
        bpy.ops.mesh.primitive_cone_add(radius1=0.055, radius2=0.0, depth=0.30,
                                        location=(0.10 * math.cos(a), 0.10 * math.sin(a), 0.98))
        lf = bpy.context.active_object; lf.name = f"husk.{c}"; assign(lf, husk)
        axis = Vector((-math.sin(a), math.cos(a), 0))
        lf.rotation_euler = Matrix.Rotation(math.radians(30), 4, axis).to_euler()
        bpy.ops.object.transform_apply(rotation=True)
        parts.append((lf, "chest"))
    # head + face (variant-driven)
    for obj in build_head(head_variant, yellow, husk, cream, eye):
        parts.append((obj, "head"))
    # limbs (both sides)
    for s, suf in ((1, "L"), (-1, "R")):
        parts.append((cyl(f"upper_arm_m.{suf}", 0.040, 0.18, (0.16 * s, 0, 0.81), husk), f"upper_arm.{suf}"))
        parts.append((cyl(f"forearm_m.{suf}", 0.035, 0.14, (0.16 * s, 0, 0.65), husk), f"forearm.{suf}"))
        parts.append((box(f"hand_m.{suf}", 0.06, 0.05, 0.06, (0.16 * s, 0, 0.54), cream), f"hand.{suf}"))
        parts.append((cyl(f"thigh_m.{suf}", 0.050, 0.21, (0.09 * s, 0, 0.445), husk), f"thigh.{suf}"))
        parts.append((cyl(f"shin_m.{suf}", 0.045, 0.25, (0.09 * s, 0, 0.215), husk), f"shin.{suf}"))
        parts.append((box(f"foot_m.{suf}", 0.11, 0.20, 0.07, (0.09 * s, 0.04, 0.04), husk), f"foot.{suf}"))
    for obj, bone in parts:
        parent_to_bone(obj, arm, bone)
    return [(o.name, b) for o, b in parts]

# ---- walk / idle (reused from Prototype A — the rig generalizes) -----------
def walk_keys():
    T, A = 0.40, 0.32
    return {
        "thigh.L": {"rot_x": [(1, +T), (7, 0), (13, -T), (19, 0), (25, +T)]},
        "thigh.R": {"rot_x": [(1, -T), (7, 0), (13, +T), (19, 0), (25, -T)]},
        # shin rotates NEGATIVE so the calf tucks backward (human knee, not a reverse/bird knee)
        "shin.L":  {"rot_x": [(1, -0.20), (7, -0.30), (13, -0.25), (19, -0.90), (25, -0.20)]},
        "shin.R":  {"rot_x": [(1, -0.90), (7, -0.25), (13, -0.20), (19, -0.30), (25, -0.90)]},
        "upper_arm.L": {"rot_x": [(1, -A), (7, 0), (13, +A), (19, 0), (25, -A)]},
        "upper_arm.R": {"rot_x": [(1, +A), (7, 0), (13, -A), (19, 0), (25, +A)]},
        "spine": {"rot_x": [(1, 0.08)]},
        "chest": {"rot_y": [(1, 0.06), (13, -0.06), (25, 0.06)]},
        "hips":  {"loc_y": [(1, 0.0), (7, 0.025), (13, 0.0), (19, 0.025), (25, 0.0)]},
    }

def idle_keys():
    return {
        "hips":        {"loc_y": [(1, 0.0), (24, 0.010), (48, 0.0)]},
        "upper_arm.L": {"rot_x": [(1, 0.0), (24, 0.05), (48, 0.0)]},
        "upper_arm.R": {"rot_x": [(1, 0.0), (24, -0.05), (48, 0.0)]},
        "head":        {"rot_y": [(1, 0.0), (24, 0.06), (48, 0.0)]},
    }

def corn_clip_meta():
    def ph(f): return round((f - 1) / 24, 5)
    ev = [
        {"frame": 1,  "phase": ph(1),  "type": "foot_plant", "foot": "L"},
        {"frame": 13, "phase": ph(13), "type": "foot_lift",  "foot": "L"},
        {"frame": 13, "phase": ph(13), "type": "foot_plant", "foot": "R"},
        {"frame": 25, "phase": ph(25), "type": "foot_lift",  "foot": "R"},
    ]
    return {
        "walk": {"loop": True, "fps": FPS, "frame_start": 1, "frame_end": 25,
                 "nominal_duration_s": round(24 / FPS, 4), "events": ev},
        "idle": {"loop": True, "fps": FPS, "frame_start": 1, "frame_end": 48,
                 "nominal_duration_s": round(47 / FPS, 4), "events": []},
    }

# ---- popcorn burst: object-animated puffs, one-shot `pop` ------------------
def build_puff(name, m):
    parts = [lowsphere(0.060, (0, 0, 0))]
    for _ in range(3):
        off = (random.uniform(-0.04, 0.04), random.uniform(-0.04, 0.04), random.uniform(-0.04, 0.04))
        parts.append(lowsphere(random.uniform(0.038, 0.055), off))
    o = join(parts); o.name = name; assign(o, m)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
    return o

def key(o, f, loc, s, rot):
    o.location = loc; o.keyframe_insert("location", frame=f)
    o.scale = (s, s, s); o.keyframe_insert("scale", frame=f)
    o.rotation_euler = rot; o.keyframe_insert("rotation_euler", frame=f)

def build_popcorn(n=22):
    random.seed(1234)
    m = M_pop()
    center = Vector((0, 0, 0.7))
    for i in range(n):
        p = build_puff(f"puff_{i:02d}", m)
        a = random.uniform(0, 2 * math.pi); rr = random.uniform(0.08, 0.38)
        fp = Vector((rr * math.cos(a), rr * math.sin(a), 0.05 + random.uniform(0, 0.03)))
        apex = Vector((fp.x * 0.6, fp.y * 0.6, 0.50 + random.uniform(0, 0.22)))
        start = center + Vector((random.uniform(-0.03, 0.03), random.uniform(-0.03, 0.03),
                                 random.uniform(-0.03, 0.03)))
        rot = (random.uniform(0, math.pi), random.uniform(0, math.pi), random.uniform(0, math.pi))
        rr03 = tuple(c * 0.3 for c in rot); rr06 = tuple(c * 0.6 for c in rot)
        key(p, 1, start, 0.02, (0, 0, 0))
        key(p, 4, start.lerp(apex, 0.3), 1.0, rr03)
        key(p, 6, apex, 1.0, rr06)
        key(p, 12, fp, 1.0, rot)
        key(p, 14, fp, 1.0, rot)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 14

def popcorn_clip_meta():
    return {"pop": {"loop": False, "one_shot": True, "fps": FPS, "frame_start": 1, "frame_end": 14,
                    "nominal_duration_s": round(13 / FPS, 4), "events": []}}

# ---- export ----------------------------------------------------------------
def export(name, mode):
    bpy.ops.object.select_all(action='SELECT')
    common = dict(export_animations=True, export_animation_mode=mode, use_selection=True)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), export_format='GLB', **common)
    dbg = OUT / "debug"; dbg.mkdir(exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(dbg / f"{name}.gltf"), export_format='GLTF_SEPARATE', **common)

def write_manifest(name, data):
    (OUT / f"{name}_manifest.json").write_text(json.dumps(data, indent=2))

# ---- main ------------------------------------------------------------------
def corn_manifest(parts, head):
    return {
        "asset": f"Kerbal-tier corn-cob person (Direction B) — head: {head}",
        "generator_script": "blender_corn.py",
        "frame": "authored Z-up; exported +Y up, metres",
        "bind": "rigid: each part object-parented to one bone; no skin weights",
        "head_variant": head,
        "clips": corn_clip_meta(),
        "bones": [b[0] for b in corn_bone_defs()],
        "parts": {n: b for n, b in parts},
        "failure_transform": {"on": "catastrophic_failure", "to": "popcorn_burst.glb",
                              "action": "despawn avatar, spawn burst at its transform"},
        "license": "clean: Blender (GPL) + authored geometry + hand-keyed motion",
    }

def build_corn(head):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = build_armature(corn_bone_defs(), "corn")
    parts = build_corn_parts(arm, head)
    make_action("walk", arm, walk_keys())
    make_action("idle", arm, idle_keys())
    arm.animation_data.action = bpy.data.actions["walk"]
    return arm, parts

def add_tuft_chain(arm):
    """Add a 2-joint 'tuft' bone chain up from the head top and re-parent the cob-head husk-tuft cones
    onto its swaying tip, so the tuft can be a VRM spring chain (WI 925). Inert in corn.glb (no action
    channels touch it); the +2 bones are the only structural change to the game-lane asset."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    t0 = eb.new("tuft.0"); t0.head = (0, 0, 1.30); t0.tail = (0, 0, 1.38)
    t0.use_connect = False; t0.parent = eb["head"]
    t1 = eb.new("tuft.1"); t1.head = (0, 0, 1.38); t1.tail = (0, 0, 1.46)
    t1.use_connect = False; t1.parent = t0
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        if o.name.startswith("tuft_"):            # the cob-head husk-tuft cones (tuft_0/1/2)
            parent_to_bone(o, arm, "tuft.1")
    return ["tuft.0", "tuft.1"]

def main():
    # VRM mode: emit corn.glb (with a husk-tuft spring bone) + corn.vrm (1.0) + corn.vrm0.vrm (0.x).
    if VRM:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import vrm_export
        arm, parts = build_corn("cob")
        joints = add_tuft_chain(arm)
        export("corn", 'ACTIONS')                       # game-lane glb (now +2 tuft bones, clips intact)
        write_manifest("corn", corn_manifest(parts, "cob"))
        p1, p0 = vrm_export.export_vrm(arm, OUT, "corn", spring_joint_bones=joints, center_bone="head")
        print(f"built corn + VRM: {OUT/'corn.glb'}, {p1}, {p0}")
        return

    # Head bake-off mode: build only the requested corn head variants.
    if HEADS:
        for hv in HEADS:
            _, parts = build_corn(hv)
            export(f"corn_{hv}", 'ACTIONS')
            write_manifest(f"corn_{hv}", corn_manifest(parts, hv))
            print(f"built corn_{hv}: {len(parts)} parts")
        return

    # --- corn person (default = cob head; owner-selected 2026-07-09) ---
    _, parts = build_corn("cob")
    export("corn", 'ACTIONS')
    write_manifest("corn", corn_manifest(parts, "cob"))
    print(f"built corn: {len(parts)} parts")

    # --- popcorn burst (failure state) ---
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_popcorn(22)
    export("popcorn_burst", 'SCENE')
    write_manifest("popcorn_burst", {
        "asset": "popcorn burst — failure state of the corn person",
        "generator_script": "blender_corn.py",
        "frame": "authored Z-up; exported +Y up, metres",
        "clips": popcorn_clip_meta(),
        "is_failure_state_of": "corn.glb",
        "license": "clean: Blender (GPL) + authored geometry + hand-keyed motion",
    })
    print("built popcorn_burst: 22 puffs")

if __name__ == "__main__":
    main()
