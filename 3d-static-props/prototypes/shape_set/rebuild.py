"""Rebuild a generated prop to a triangle budget and bake its colour, headless.

blender -b --python rebuild.py -- SRC.glb NORM.json TRIS TEX OUTDIR [planar|box]

Imports the dense mesh, applies the normaliser's matrix, makes a low copy by voxel remesh and
collapse decimation, unwraps it, bakes the dense mesh's base colour onto it (Cycles, selected to
active), exports the low prop as a glb with the bake as its only texture (roughness 1, metallic 0),
and renders the dense and low props from the same three cameras.
"""
import json
import math
import os
import sys
import time

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
src, norm_path, tris, tex, outdir = argv[0], argv[1], int(argv[2]), int(argv[3]), argv[4]
# planar: a coarser remesh, then the collapse, then faces within 8 degrees merged flat (hard-surface props)
planar = len(argv) > 5 and argv[5] == "planar"
# box: in place of the remesh, a box fitted to the dense mesh's bounds with bevelled edges (TRIS unused)
box = len(argv) > 5 and argv[5] == "box"
mode = argv[5] if len(argv) > 5 and argv[5] in ("planar", "box") else ""
stem = os.environ.get("REBUILD_STEM", "crate")
os.makedirs(outdir, exist_ok=True)
log = {"source": src, "target_tris": tris, "texture": tex}
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
high = bpy.context.view_layer.objects.active
high.name = "high"
# parent transforms from the importer, then the normaliser's matrix
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
m = json.load(open(norm_path))["matrix"]
high.data.transform(mathutils.Matrix(m))
high.data.update()
bpy.context.view_layer.update()
log["high_tris"] = sum(len(p.vertices) - 2 for p in high.data.polygons)
dims = high.dimensions.copy()
size = max(dims)
log["high_dims"] = [round(v, 4) for v in dims]
log["t_import"] = round(time.time() - t0, 1)

# low: a copy, voxel remeshed, collapsed to the budget, triangulated
t1 = time.time()
if box:
    lo_c = mathutils.Vector([min(v.co[i] for v in high.data.vertices) for i in range(3)])
    hi_c = mathutils.Vector([max(v.co[i] for v in high.data.vertices) for i in range(3)])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo_c + hi_c) / 2)
    low = bpy.context.view_layer.objects.active
    low.name = "low"
    low.scale = hi_c - lo_c
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bev = low.modifiers.new("bevel", "BEVEL")
    bev.width = size * 0.04
    bev.segments = 2
    bpy.ops.object.modifier_apply(modifier="bevel")
    log["remesh_tris"] = 0
    tri = low.modifiers.new("tri", "TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier="tri")
else:
    low = high.copy()
    low.data = high.data.copy()
    low.name = "low"
    bpy.context.scene.collection.objects.link(low)
    low.data.materials.clear()
    mod = low.modifiers.new("remesh", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = size / (40 if planar else 96)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.ops.object.modifier_apply(modifier="remesh")
    log["remesh_tris"] = sum(len(p.vertices) - 2 for p in low.data.polygons)
    dec = low.modifiers.new("decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = tris / max(1, log["remesh_tris"])
    dec.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier="decimate")
    if planar:
        pl = low.modifiers.new("planar", "DECIMATE")
        pl.decimate_type = "DISSOLVE"
        pl.angle_limit = math.radians(8)
        bpy.ops.object.modifier_apply(modifier="planar")
    tri = low.modifiers.new("tri", "TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier="tri")
log["low_tris"] = len(low.data.polygons)
# the remesh can leave the foot a little under z 0: stand it back on the ground
foot = min(v.co.z for v in low.data.vertices)
low.data.transform(mathutils.Matrix.Translation((0, 0, -foot)))
log["foot_lifted"] = round(-foot, 4)
# smooth across faces meeting under 30 degrees, a hard edge above (the crate's corners)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
log["t_rebuild"] = round(time.time() - t1, 1)

# unwrap
t2 = time.time()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")
log["t_unwrap"] = round(time.time() - t2, 1)

# bake target: an image filled with a marker colour, so texels the bake never wrote can be counted
img = bpy.data.images.new("baked", tex, tex, alpha=False)
img.generated_color = (1.0, 0.0, 1.0, 1.0)
mat = bpy.data.materials.new("prop")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 1.0
bsdf.inputs["Metallic"].default_value = 0.0
node = nt.nodes.new("ShaderNodeTexImage")
node.image = img
nt.nodes.active = node
low.data.materials.append(mat)

# the dense prop flattened to Look 1's material (base colour only, roughness 1, metallic 0): Cycles'
# diffuse colour pass is base colour x (1 - metallic), so a connected metallic map darkens the bake;
# the renders then differ only by the rebuild and the bake
for slot in high.material_slots:
    hn = slot.material.node_tree
    for b in [n for n in hn.nodes if n.type == "BSDF_PRINCIPLED"]:
        for name, value in (("Metallic", 0.0), ("Roughness", 1.0)):
            for link in list(b.inputs[name].links):
                hn.links.remove(link)
            b.inputs[name].default_value = value
        for link in list(b.inputs["Normal"].links):
            hn.links.remove(link)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 4
bake = scene.render.bake
bake.use_selected_to_active = True
bake.cage_extrusion = size * 0.02
# a fitted box stands off the walls by the protrusions (caps, latches), so its rays reach further
bake.max_ray_distance = size * (0.2 if box else 0.06)
bake.margin = 4
bake.use_pass_direct = False
bake.use_pass_indirect = False
bake.use_pass_color = True
bpy.ops.object.select_all(action="DESELECT")
high.select_set(True)
low.select_set(True)
bpy.context.view_layer.objects.active = low
t3 = time.time()
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
log["t_bake"] = round(time.time() - t3, 1)
img.filepath_raw = os.path.join(outdir, f"baked_{tex}.png")
img.file_format = "PNG"
img.save()
img.pack()
# linked only after the bake, so the image is not both read and written by it
nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])

# export the low prop alone
bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
glb = os.path.join(outdir, f"{stem}_{tris}{('_' + mode) if mode else ''}.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_yup=True,
                          export_apply=True, export_image_format="AUTO", export_materials="EXPORT")
log["glb"] = glb
log["glb_bytes"] = os.path.getsize(glb)

# renders: the same three cameras on the dense and low props, under an even white world
t4 = time.time()
scene.cycles.samples = 32
scene.render.resolution_x = scene.render.resolution_y = 480
scene.render.film_transparent = True
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
scene.world = world
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
centre = mathutils.Vector((0, 0, dims.z / 2))
views = {"front": (35, 20), "side": (125, 15), "above": (215, 55)}
renders = {}
for which, obj, hide in (("high", high, low), ("low", low, high)):
    obj.hide_render = False
    hide.hide_render = True
    for name, (az, el) in views.items():
        a, e = math.radians(az), math.radians(el)
        d = size * 2.4
        cam.location = centre + mathutils.Vector((d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e)))
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(outdir, f"render_{which}_{tris}{('_' + mode) if mode else ''}_{name}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        renders[f"{which}_{name}"] = path
# the same two props under a low sun and a dim sky, the game's kind of light: the even world above
# hides facets and folds that a raking sun shows (WI 2091)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(55), 0, math.radians(150))
scene.collection.objects.link(sun)
a, e = math.radians(35), math.radians(20)
d = size * 2.4
cam.location = centre + mathutils.Vector((d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e)))
cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
for which, obj, hide in (("high", high, low), ("low", low, high)):
    obj.hide_render = False
    hide.hide_render = True
    path = os.path.join(outdir, f"render_{which}_{tris}{('_' + mode) if mode else ''}_sun.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    renders[f"{which}_sun"] = path
log["renders"] = renders
log["t_render"] = round(time.time() - t4, 1)
log["t_total"] = round(time.time() - t0, 1)
log["mode"] = mode or "collapse"
json.dump(log, open(os.path.join(outdir, f"rebuild_{tris}{('_' + mode) if mode else ''}.json"), "w"), indent=1)
print("REBUILD", json.dumps(log))
