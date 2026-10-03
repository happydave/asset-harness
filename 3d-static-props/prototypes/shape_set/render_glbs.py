"""Render glbs from rebuild.py's cameras, under the same even white world.

blender -b --python render_glbs.py -- OUTDIR A.glb B.glb ...  (writes OUTDIR/<stem>_<view>.png)
"""
import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
outdir, files = argv[0], argv[1:]
os.makedirs(outdir, exist_ok=True)
views = {"front": (35, 20), "side": (125, 15), "above": (215, 55)}
for path in files:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo = mathutils.Vector((1e9,) * 3)
    hi = mathutils.Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector(map(min, lo, w))
            hi = mathutils.Vector(map(max, hi, w))
    size = max(hi - lo)
    centre = (lo + hi) / 2
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.render.resolution_x = scene.render.resolution_y = 480
    scene.render.film_transparent = True
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    scene.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    stem = os.path.splitext(os.path.basename(path))[0]
    for name, (az, el) in views.items():
        a, e = math.radians(az), math.radians(el)
        d = size * 2.4
        cam.location = centre + mathutils.Vector((d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e)))
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(outdir, f"{stem}_{name}.png")
        bpy.ops.render.render(write_still=True)
