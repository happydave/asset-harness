"""Headless Blender cleanup for raw image-to-3D meshes: import glTF -> decimate -> export glTF.

Turns a dense MoGe/Hunyuan/TripoSR mesh into a game-ready LOD (textures/UVs preserved by the
collapse decimator). Run on a box with Blender:

    blender --background --python blender_decimate.py -- IN.glb OUT.glb [ratio]

`ratio` is the decimate collapse ratio (0..1); default 0.02 (~50x reduction).
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
inp, outp = argv[0], argv[1]
ratio = float(argv[2]) if len(argv) > 2 else 0.02


def stats():
    v = f = 0
    for o in bpy.data.objects:
        if o.type == "MESH":
            v += len(o.data.vertices)
            f += len(o.data.polygons)
    return v, f


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp)
v0, f0 = stats()

for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    bpy.context.view_layer.objects.active = o
    m = o.modifiers.new("decimate", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=m.name)

v1, f1 = stats()
print(f"DECIMATE_RESULT in_verts={v0} in_faces={f0} out_verts={v1} out_faces={f1} ratio={ratio}")

bpy.ops.export_scene.gltf(filepath=outp, export_format="GLB")
print(f"EXPORTED {outp}")
