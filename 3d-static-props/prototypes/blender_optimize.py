"""Headless Blender game-ready optimize for glTF: downscale embedded textures (+ optional decimate).

The cleanup pass that makes a generated glb game-light: resize each embedded image to a max
dimension and re-encode the export as JPEG (big size win for opaque base-color assets), and
optionally collapse-decimate the geometry. (KTX2/Basis is the future runtime-texture step.)

    blender --background --python blender_optimize.py -- IN.glb OUT.glb [max_tex] [quality] [ratio]

max_tex: texture max dimension (default 512); quality: JPEG 0-100 (default 85);
ratio: decimate collapse ratio (default 1.0 = no decimation).
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
inp, outp = argv[0], argv[1]
max_tex = int(argv[2]) if len(argv) > 2 else 512
quality = int(argv[3]) if len(argv) > 3 else 85
ratio = float(argv[4]) if len(argv) > 4 else 1.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp)

# optional decimate
faces_before = faces_after = 0
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    faces_before += len(o.data.polygons)
if ratio < 1.0:
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("dec", "DECIMATE")
        m.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=m.name)
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    faces_after += len(o.data.polygons)

# downscale textures
resized = []
for img in bpy.data.images:
    w, h = img.size
    if w == 0 or h == 0:
        continue
    if max(w, h) > max_tex:
        s = max_tex / max(w, h)
        img.scale(max(1, round(w * s)), max(1, round(h * s)))
        resized.append((img.name, (w, h), img.size[:]))

bpy.ops.export_scene.gltf(
    filepath=outp, export_format="GLB",
    export_image_format="JPEG", export_jpeg_quality=quality,
)
print(f"OPTIMIZED {outp} faces {faces_before}->{faces_after} tex<= {max_tex} q{quality} "
      f"resized={resized}")
