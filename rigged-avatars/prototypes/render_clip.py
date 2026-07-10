#!/usr/bin/env python3
"""Render frames of a named clip from a glb (auto-framed), for visual review. EEVEE, headless on `ai2`:

    blender --background --python render_clip.py -- --glb OUT/corn.glb --out OUT \
            --clip walk --prefix corn_walk --frames 1,4,7,10,13,16,19,22

Auto-frames the imported mesh bbox, so it works for a standing character or a low burst pile.
If --clip is omitted (or not found), renders the current/first animation. Validates the round-trip.
"""
import bpy, sys, math
from pathlib import Path
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default

GLB = Path(arg("--glb", "/tmp/out/corn.glb"))
OUT = Path(arg("--out", "/tmp/out")); OUT.mkdir(parents=True, exist_ok=True)
CLIP = arg("--clip")
PREFIX = arg("--prefix", GLB.stem)
FRAMES = [int(x) for x in arg("--frames", "1,4,7,10,13,16,19,22").split(",")]
PORTRAIT = "--portrait" in argv   # frame the head region, more head-on

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))

# select clip
arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
clip = None
if CLIP:
    clip = next((a for a in bpy.data.actions if CLIP.lower() in a.name.lower()), None)
if clip and arm:
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = clip
    print("clip:", clip.name, "range", clip.frame_range[:])
elif clip:  # object-animated (no armature) — action already bound on import; SCENE-mode plays via frames
    print("clip:", clip.name, "range", clip.frame_range[:])

# combined world-space bbox swept over ALL rendered frames (so a moving/scattering clip stays framed)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mn = Vector((1e9, 1e9, 1e9)); mx = -mn
for f in FRAMES:
    bpy.context.scene.frame_set(f)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
center = (mn + mx) / 2
size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 0.2)
if PORTRAIT:                                    # zoom to the head, look more head-on
    center = Vector((center.x, center.y, mx.z - 0.16)); size = 0.42
    camdir, distf = Vector((0.35, 1.0, 0.12)), 1.9
else:
    camdir, distf = Vector((0.9, 1.3, 0.55)), 2.0

# ground, camera (front-3/4), sun, world
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, mn.z))
gp = bpy.context.active_object
gm = bpy.data.materials.new("ground"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.20, 0.21, 0.23, 1)
gp.data.materials.append(gm)

target = bpy.data.objects.new("tgt", None); target.location = center
bpy.context.scene.collection.objects.link(target)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = center + camdir.normalized() * size * distf
tc = cam.constraints.new('TRACK_TO'); tc.target = target
tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.data.energy = 4.5; sun.rotation_euler = (math.radians(55), 0, math.radians(35))
bpy.context.scene.collection.objects.link(sun)
world = bpy.data.worlds.new("w"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.09, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
bpy.context.scene.world = world

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = sc.render.resolution_y = 640
sc.render.film_transparent = False
for i, f in enumerate(FRAMES):
    sc.frame_set(f)
    sc.render.filepath = str(OUT / f"{PREFIX}_{i:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered frame", f)
