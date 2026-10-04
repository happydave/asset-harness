"""One arm's rebuild in Blender, headless: blender -b --python blender_rebuild.py -- CONFIG.json

The config names the source, the normaliser's matrix, the arm (`generic`, `box`, `planar`, or `given`
with a geometry glb built outside Blender), the budget, the texture size, the output folder and stem, the
source's part count (the generic arm's voxel choice), the box arm's fitted bounds, and the light rig.

Imports the dense source, applies the matrix, builds the low prop, unwraps it, bakes the source's base
colour onto it (Cycles, selected to active), exports it as a glb with the bake as its only texture, and
renders source and rebuild from the same cameras: four views under an even white world (the colour row),
and two views under each of the rig's lightings (the consumer-light sheet).
"""
import bmesh
import json
import math
import os
import sys
import time

import bpy
import mathutils

cfg = json.load(open(sys.argv[sys.argv.index("--") + 1]))
out, stem, mode = cfg["outdir"], cfg["stem"], cfg["mode"]
tris, tex = int(cfg["budget"]), int(cfg["texture"])
os.makedirs(out, exist_ok=True)
log = {"mode": mode, "budget": tris, "texture": tex}
t0 = time.time()


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def apply(obj, mod):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def join_imported():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name not in ("high",)]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def islands(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    seen, count = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        count += 1
        stack = [f]
        while stack:
            g = stack.pop()
            if g.index in seen:
                continue
            seen.add(g.index)
            for e in g.edges:
                stack.extend(h for h in e.link_faces if h.index not in seen)
    bm.free()
    return count


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=cfg["source"])
high = join_imported()
high.name = "high"
high.data.transform(mathutils.Matrix(cfg["matrix"]))
high.data.update()
bpy.context.view_layer.update()
dims = high.dimensions.copy()
size = max(dims)
log["high_tris"] = tri_count(high)

t1 = time.time()
if mode == "box":
    if cfg.get("box_bounds"):
        # fitted to the body by the stage (parts.box_bounds), in the same normalised frame
        lo_c, hi_c = (mathutils.Vector(v) for v in cfg["box_bounds"])
    else:
        lo_c = mathutils.Vector([min(v.co[i] for v in high.data.vertices) for i in range(3)])
        hi_c = mathutils.Vector([max(v.co[i] for v in high.data.vertices) for i in range(3)])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo_c + hi_c) / 2)
    low = bpy.context.view_layer.objects.active
    low.scale = hi_c - lo_c
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bev = low.modifiers.new("bevel", "BEVEL")
    bev.width = size * 0.04
    bev.segments = 2
    apply(low, bev)
elif mode == "given":
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=cfg["given"])
    new = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    low = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    low.data.materials.clear()
else:
    # generic and planar: a voxel remesh, then a collapse to the budget. The generic arm takes the
    # finest voxel whose remesh has no more pieces than the source has parts, coarsening step by step
    ladder = [40] if mode == "planar" else [96, 72, 56, 48]
    tried = []
    low = None
    for div in ladder:
        cand = high.copy()
        cand.data = high.data.copy()
        bpy.context.scene.collection.objects.link(cand)
        cand.data.materials.clear()
        rm = cand.modifiers.new("remesh", "REMESH")
        rm.mode = "VOXEL"
        rm.voxel_size = size / div
        apply(cand, rm)
        n = islands(cand)
        tried.append({"divisor": div, "pieces": n, "tris": tri_count(cand)})
        if low is not None:
            bpy.data.objects.remove(low, do_unlink=True)
        low = cand
        if n <= int(cfg.get("source_parts", 1)) or mode == "planar":
            break
    log["voxel_ladder"] = tried
    dec = low.modifiers.new("decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = min(1.0, tris / max(1, tri_count(low)))
    dec.use_collapse_triangulate = True
    apply(low, dec)
    # the collapse leaves crumbs of a face or two where the remesh had thin bits: islands under 0.5 % of
    # the rebuild's area are dropped as debris, and their count recorded
    bm = bmesh.new()
    bm.from_mesh(low.data)
    total = sum(f.calc_area() for f in bm.faces)
    seen, crumbs = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        isl, stack = [], [f]
        while stack:
            g = stack.pop()
            if g in seen:
                continue
            seen.add(g)
            isl.append(g)
            for e in g.edges:
                stack.extend(h for h in e.link_faces if h not in seen)
        if sum(g.calc_area() for g in isl) < 0.005 * total:
            crumbs.append(isl)
    bmesh.ops.delete(bm, geom=[g for isl in crumbs for g in isl], context="FACES")
    bm.to_mesh(low.data)
    bm.free()
    log["debris_islands_dropped"] = len(crumbs)
    if mode == "planar":
        pl = low.modifiers.new("planar", "DECIMATE")
        pl.decimate_type = "DISSOLVE"
        pl.angle_limit = math.radians(8)
        apply(low, pl)
low.name = "low"
tri = low.modifiers.new("tri", "TRIANGULATE")
apply(low, tri)
log["low_tris"] = len(low.data.polygons)
foot = min(v.co.z for v in low.data.vertices)
low.data.transform(mathutils.Matrix.Translation((0, 0, -foot)))
log["foot_lifted"] = round(-foot, 5)
bpy.context.view_layer.objects.active = low
bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
log["t_rebuild"] = round(time.time() - t1, 1)

bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")

# bake target: filled with a marker colour, so texels the bake never wrote can be counted
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
# the source flattened to base colour (roughness 1, metallic 0): Cycles' diffuse colour pass is base
# colour x (1 - metallic), so a connected metallic map darkens the bake
for slot in high.material_slots:
    if not slot.material or not slot.material.use_nodes:
        continue
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
scene.cycles.seed = 0
bake = scene.render.bake
bake.use_selected_to_active = True
bake.cage_extrusion = size * 0.02
# a fitted box or a lathe stands off the surface by the protrusions, so its rays reach further
bake.max_ray_distance = size * (0.2 if mode == "box" else 0.1 if mode == "given" else 0.06)
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
img.filepath_raw = os.path.join(out, "baked.png")
img.file_format = "PNG"
img.save()
img.pack()
# linked only after the bake, so the image is not both read and written by it
nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])

bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
glb = os.path.join(out, f"{stem}_lod0.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_yup=True,
                          export_apply=True, export_image_format="AUTO", export_materials="EXPORT")
log["lod0"] = glb

t4 = time.time()
scene.cycles.samples = 32
scene.render.resolution_x = scene.render.resolution_y = 400
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
scene.world = world
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
centre = mathutils.Vector((0, 0, dims.z / 2))


def aim(az, el):
    a, e = math.radians(az), math.radians(el)
    d = size * 2.4
    cam.location = centre + mathutils.Vector((d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e)))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()


def shoot(prefix, views):
    paths = {}
    for which, obj, hide in (("source", high, low), ("rebuild", low, high)):
        obj.hide_render = False
        hide.hide_render = True
        for name, (az, el) in views.items():
            aim(az, el)
            path = os.path.join(out, "renders", f"{prefix}_{which}_{name}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            paths[f"{which}_{name}"] = path
    return paths


renders = {}
bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
bg.inputs["Strength"].default_value = 1.0
scene.view_settings.exposure = 0.0
even = {"front": (35, 20), "side": (125, 15), "back": (215, 20), "above": (305, 55)}
renders["even"] = shoot("even", even)

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
scene.collection.objects.link(sun)
for name, light in cfg["rig"]["lightings"].items():
    el, az = math.radians(light["sun_elevation_deg"]), math.radians(light["sun_azimuth_deg"])
    # a sun light shines along its local -Z: aim -Z from the sun's direction toward the ground
    direction = mathutils.Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    sun.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    sun.data.color = light["sun_colour"]
    sun.data.energy = light["sun_strength"]
    bg.inputs["Color"].default_value = (*light["ambient_colour"], 1.0)
    bg.inputs["Strength"].default_value = light["ambient_strength"]
    scene.view_settings.exposure = light.get("exposure", 0.0)
    renders[name] = shoot(name, {"front": (35, 20), "side": (125, 15)})
log["renders"] = renders
log["t_render"] = round(time.time() - t4, 1)
log["size"] = round(size, 5)
log["t_total"] = round(time.time() - t0, 1)
json.dump(log, open(os.path.join(out, "blender.json"), "w"), indent=1)
print("REBUILD", json.dumps({k: v for k, v in log.items() if k != "renders"}))
