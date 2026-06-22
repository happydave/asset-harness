"""Headless Blender turntable preview of a glTF mesh — render a few angles to PNG.

For eyeballing image-to-3D output (shape/orientation/texture) without a GUI.

    blender --background --python blender_render_preview.py -- IN.glb OUT_BASE
"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
inp, outbase = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp)

mins = Vector((1e9, 1e9, 1e9))
maxs = Vector((-1e9, -1e9, -1e9))
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mins[i] = min(mins[i], w[i])
            maxs[i] = max(maxs[i], w[i])
center = (mins + maxs) / 2
radius = max((maxs - mins)) / 2 or 1.0

world = bpy.data.worlds.new("w")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 1.2  # ambient

sun_d = bpy.data.lights.new("sun", "SUN")
sun_d.energy = 3.0
sun = bpy.data.objects.new("sun", sun_d)
bpy.context.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
bpy.context.collection.objects.link(cam)
scene = bpy.context.scene
scene.camera = cam
scene.render.engine = "CYCLES"
scene.cycles.samples = 24
scene.cycles.device = "CPU"
scene.render.resolution_x = scene.render.resolution_y = 640
scene.cycles.use_denoising = False  # ai2's Blender build has no OpenImageDenoiser
try:
    bpy.context.view_layer.cycles.use_denoising = False
except Exception:
    pass


def render(az, el, name):
    d = radius * 3.0
    a, e = math.radians(az), math.radians(el)
    cam.location = center + Vector(
        (d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e))
    )
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = f"{outbase}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print(f"rendered {name}")


render(55, 20, "oblique")
render(0, 88, "top")
render(55, -10, "below")
print("DONE")
