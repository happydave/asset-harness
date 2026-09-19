"""Render a GLB from four angles with Blender, and report mesh statistics.

Independent of the stack that produced the mesh: the point is to look at the artifact
with something other than ComfyUI's own renderer.

  blender -b -P render_glb.py -- <in.glb> <out_prefix>
"""
import bpy, sys, os, math, json

argv = sys.argv[sys.argv.index("--") + 1:]
src, out_prefix = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
stats = {"source": src, "objects": len(meshes), "verts": 0, "faces": 0, "tris": 0}
for o in meshes:
    m = o.data
    stats["verts"] += len(m.vertices)
    stats["faces"] += len(m.polygons)
    stats["tris"] += sum(len(p.vertices) - 2 for p in m.polygons)

# Fit everything into view
coords = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
if coords:
    xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
    center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2)
    radius = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)) / 2 or 1.0
    stats["bbox"] = {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}
else:
    center, radius = (0, 0, 0), 1.0

world = bpy.data.worlds.new("w"); bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 1.5

light_data = bpy.data.lights.new("key", type="SUN"); light_data.energy = 3.0
light = bpy.data.objects.new("key", light_data); bpy.context.scene.collection.objects.link(light)
light.rotation_euler = (math.radians(50), 0, math.radians(30))

cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data); bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam

# Aim with a TRACK_TO constraint rather than hand-rolled Euler angles: the hand-rolled
# version rendered an empty frame on the control mesh, which would have read as a bad mesh.
target = bpy.data.objects.new("target", None)
bpy.context.scene.collection.objects.link(target)
target.location = center
con = cam.constraints.new(type="TRACK_TO")
con.target = target
con.track_axis = "TRACK_NEGATIVE_Z"
con.up_axis = "UP_Y"

scene = bpy.context.scene
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.film_transparent = False

dist = radius * 3.0
for ang in (0, 90, 180, 270):
    a = math.radians(ang)
    cam.location = (center[0] + dist * math.cos(a),
                    center[1] + dist * math.sin(a),
                    center[2] + dist * 0.45)
    bpy.context.view_layer.update()
    scene.render.filepath = f"{out_prefix}_{ang:03d}.png"
    bpy.ops.render.render(write_still=True)

print("MESHSTATS " + json.dumps(stats))
