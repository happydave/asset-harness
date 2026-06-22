"""Headless Blender: build a terrain mesh by displacing a grid with a heightmap, texture it, export glTF.

The clean, controllable terrain path (vs monocular reconstruction): a regular grid gets a Displace
modifier driven by a grayscale heightmap (white=high), then the albedo is applied as base color.
The heightmap source is pluggable (luminance-derived here; could be MoGe depth or a dedicated map).

    blender --background --python blender_displace.py -- HEIGHT.png ALBEDO.png OUT.glb [strength] [size] [subdiv]
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
height_path, albedo_path, out_path = argv[0], argv[1], argv[2]
strength = float(argv[3]) if len(argv) > 3 else 2.0
size = float(argv[4]) if len(argv) > 4 else 10.0
subdiv = int(argv[5]) if len(argv) > 5 else 200

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdiv, y_subdivisions=subdiv, size=size)
obj = bpy.context.active_object

# heightmap as a non-color displacement texture
himg = bpy.data.images.load(height_path)
himg.colorspace_settings.name = "Non-Color"
htex = bpy.data.textures.new("height", "IMAGE")
htex.image = himg

m = obj.modifiers.new("disp", "DISPLACE")
m.texture = htex
m.texture_coords = "UV"
m.strength = strength
m.mid_level = 0.5
bpy.context.view_layer.objects.active = obj
bpy.ops.object.modifier_apply(modifier=m.name)
bpy.ops.object.shade_smooth()

# albedo material (base color from the same top-down image, UV 0..1 across the grid)
mat = bpy.data.materials.new("terrain")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(albedo_path)
mat.node_tree.links.new(bsdf.inputs["Base Color"], tex.outputs["Color"])
obj.data.materials.append(mat)

faces = len(obj.data.polygons)
bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB")
print(f"DISPLACED_EXPORTED {out_path} faces={faces} strength={strength} size={size} subdiv={subdiv}")
