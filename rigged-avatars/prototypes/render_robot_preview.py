#!/usr/bin/env python3
"""Render a walk contact-sheet from the exported robot.glb — validates the glTF round-trip (the glb
actually imports and animates) and gives a visual-review artifact. EEVEE, headless on `ai2`:

    blender --background --python render_robot_preview.py -- --glb DIR/robot.glb --out DIR

Renders 8 evenly-spaced frames of the `walk` clip as walk_00..07.png (front-3/4 view).
"""
import bpy, sys, math
from pathlib import Path
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = Path(argv[argv.index("--glb") + 1]) if "--glb" in argv else Path("/tmp/robot/robot.glb")
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/robot")
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))

# activate the walk clip on the imported armature
arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
walk = next((a for a in bpy.data.actions if "walk" in a.name.lower()), None)
if arm and walk:
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = walk
    print("walk action:", walk.name, "range", walk.frame_range[:])

# ground
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
gp = bpy.context.active_object
gm = bpy.data.materials.new("ground"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.20, 0.21, 0.23, 1)
gp.data.materials.append(gm)

# camera (front-3/4: character faces +Y, so put cam in +Y and to its left, looking at chest height)
target = bpy.data.objects.new("tgt", None); target.location = (0, 0, 0.95)
bpy.context.scene.collection.objects.link(target)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = Vector((2.6, 3.4, 1.5))
tc = cam.constraints.new('TRACK_TO'); tc.target = target
tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# light + world
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
for i, f in enumerate([1, 4, 7, 10, 13, 16, 19, 22]):
    sc.frame_set(f)
    sc.render.filepath = str(OUT / f"walk_{i:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered frame", f)
