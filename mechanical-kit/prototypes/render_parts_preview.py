#!/usr/bin/env python3
"""Render a thumbnail per part glb for visual verification (EEVEE, headless on `ai2`):
  blender --background --python render_parts_preview.py -- --in DIR --out DIR
One iso-view PNG per <name>.glb; montaged locally by generate_parts orchestration.
"""
import bpy, sys, math
from pathlib import Path
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
IN = Path(argv[argv.index("--in") + 1]) if "--in" in argv else Path("/tmp/mk_parts")
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/mk_preview")
OUT.mkdir(parents=True, exist_ok=True)


def render_one(glb: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        return
    # combined world-space bbox
    mn = Vector((1e9, 1e9, 1e9)); mx = -mn
    for o in meshes:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    center = (mn + mx) / 2
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 0.1)

    target = bpy.data.objects.new("tgt", None); target.location = center
    bpy.context.scene.collection.objects.link(target)
    cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = center + Vector((1.0, 0.8, 1.2)).normalized() * size * 3.2
    tc = cam.constraints.new('TRACK_TO'); tc.target = target
    tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'
    bpy.context.scene.camera = cam

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
    sun.data.energy = 4.0; sun.rotation_euler = (math.radians(55), 0, math.radians(40))
    bpy.context.scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.16, 0.16, 0.18, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    bpy.context.scene.world = world

    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = sc.render.resolution_y = 320
    sc.render.film_transparent = False
    sc.render.filepath = str(OUT / f"{glb.stem}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", glb.stem)


for g in sorted(IN.glob("*.glb")):
    render_one(g)
