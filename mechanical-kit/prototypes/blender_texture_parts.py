#!/usr/bin/env python3
"""Skin the v1 rover parts with AI PBR materials (the "AI surface" half of mechanical-kit). Headless
on `ai2`:  blender --background --python blender_texture_parts.py -- --in DIR --materials DIR --out DIR

Per part: import the v1 glb (geometry/orientation/origin already correct), UV-unwrap, bind a
Principled material from the pbr-materials map set (albedo + tangent normal + packed metallic-
roughness, Bevy convention G=rough/B=metal), tile via a Mapping scale, and re-export a textured glb.
Embedded textures are downscaled to 256 px (parts are small) to keep glbs lean.

Revolved parts (tire/rim) get a **cylindrical** unwrap about their axle so the tread wraps
circumferentially and the brushed grain follows the surface; the rest use smart-project. The
cylindrical unwrap is computed per-vertex (deterministic, view-independent — `uv.cylinder_project`
is viewport-dependent and unreliable headless): u = angle about the axis (0..1), v = position along
it; per-axis tiling comes from the Mapping node (sx around, sy along).
"""
import bpy, bmesh, sys, math
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(flag, default): return argv[argv.index(flag) + 1] if flag in argv else default
IN = Path(arg("--in", "/tmp/mk_parts"))
MATS = Path(arg("--materials", "/tmp/mk_materials"))
OUT = Path(arg("--out", "/tmp/mk_parts_tex")); OUT.mkdir(parents=True, exist_ok=True)
ONLY = arg("--only", None)
ONLY = ONLY.split(",") if ONLY else None
TEX = 256  # embedded texture size

# part -> material set, unwrap method, (and axis for cyl), tiling (sx around, sy along)
SKIN = {
    "tire": dict(mat="rubber", uw="cyl", axis="X", sx=8.0, sy=1.0),
    "rim": dict(mat="metal_panel", uw="cyl", axis="X", sx=5.0, sy=1.0),
    "suspension": dict(mat="metal_panel", uw="smart", sx=3.0, sy=3.0),
    "seat": dict(mat="seat_fabric", uw="smart", sx=2.0, sy=2.0),
    "antenna": dict(mat="metal_panel", uw="smart", sx=2.0, sy=2.0),
    "solar_panel": dict(mat="solar_cells", uw="smart", sx=2.0, sy=2.0),
    "bumper": dict(mat="metal_panel", uw="smart", sx=3.0, sy=3.0),
    "motor": dict(mat="motor_casing", uw="smart", sx=2.0, sy=2.0),
    "battery": dict(mat="battery", uw="smart", sx=2.0, sy=2.0),
    "seat_leather": dict(mat="leather_light", uw="smart", sx=2.0, sy=2.0),
    "solar_panel_2x1": dict(mat="solar_cells_2x1", uw="smart", sx=2.0, sy=2.0),
    # leather wrap follows the rim: toroidal unwrap about the wheel axis Z (major_radius 0.18 at
    # cell 0.5). u = around the wheel (stitched panels), v = around the rim tube.
    "steering_wheel": dict(mat="leather_light", uw="toroidal", axis="Z", major=0.18, sx=10.0, sy=1.0),
    # rocket-domain (axial parts: cylindrical about +Y)
    "fuel_tank": dict(mat="white_hull", uw="cyl", axis="Y", sx=3.0, sy=2.0),
    "nose_cone": dict(mat="white_hull", uw="cyl", axis="Y", sx=3.0, sy=2.0),
    "engine_bell": dict(mat="heat_metal", uw="cyl", axis="Y", sx=4.0, sy=1.5),
    "decoupler": dict(mat="metal_panel", uw="cyl", axis="Y", sx=6.0, sy=1.0),
    "fin": dict(mat="metal_panel", uw="smart", sx=2.0, sy=2.0),
    # fittings
    "hatch_round": dict(mat="metal_panel", uw="smart", sx=1.5, sy=1.5),
    "hatch_rect": dict(mat="metal_panel", uw="smart", sx=1.5, sy=1.5),
    "dish_small": dict(mat="white_hull", uw="smart", sx=2.0, sy=2.0),
    "dish_large": dict(mat="white_hull", uw="smart", sx=3.0, sy=3.0),
    "tablet": dict(mat="screen_ui", uw="smart", sx=1.0, sy=1.0),   # screen shows once per face
}

# Split parts (WI 666): per sub-object skin specs, keyed by glTF node name. These parts are
# NOT joined — each piece keeps its own node and material. Role tags are re-asserted by node
# name on export so they survive regardless of import-extras fidelity.
SPLIT_SKIN = {
    "battery": {
        "battery_body": dict(mat="battery", uw="smart", sx=2.0, sy=2.0),
        "battery_lid": dict(mat="battery", uw="smart", sx=2.0, sy=2.0),
        "battery_terminal_pos": dict(mat="metal_panel", uw="smart", sx=2.0, sy=2.0),
        "battery_terminal_neg": dict(mat="metal_panel", uw="smart", sx=2.0, sy=2.0),
    },
}
SPLIT_TAGS = {
    "battery": {
        "battery_body": {"role": "body"},
        "battery_lid": {"role": "lid"},
        "battery_terminal_pos": {"role": "terminal", "polarity": "positive"},
        "battery_terminal_neg": {"role": "terminal", "polarity": "negative"},
    },
}


def cylindrical_uv(obj, axis):
    """Per-vertex cylindrical unwrap about `axis` (object-local). u = angle (0..1), v = along-axis."""
    ai = {"X": 0, "Y": 1, "Z": 2}[axis]
    p0, p1 = [i for i in (0, 1, 2) if i != ai]   # the two perpendicular axes
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    uvl = bm.loops.layers.uv.verify()
    amin = min(v.co[ai] for v in bm.verts)
    alen = max(max(v.co[ai] for v in bm.verts) - amin, 1e-6)
    for face in bm.faces:
        us = []
        for loop in face.loops:
            co = loop.vert.co
            u = math.atan2(co[p1], co[p0]) / (2 * math.pi) + 0.5   # 0..1 around the axle
            loop[uvl].uv = (u, (co[ai] - amin) / alen)
            us.append(u)
        if max(us) - min(us) > 0.5:                # face straddles the atan2 seam — make it continuous
            for loop in face.loops:
                if loop[uvl].uv.x < 0.5:
                    loop[uvl].uv.x += 1.0
    bm.to_mesh(me); bm.free()


def toroidal_uv(obj, axis, major_radius):
    """Per-vertex toroidal unwrap (for a leather-wrapped rim): u = angle around the wheel axis,
    v = angle around the rim tube. `major_radius` is the torus major radius in object units."""
    ai = {"X": 0, "Y": 1, "Z": 2}[axis]
    p0, p1 = [i for i in (0, 1, 2) if i != ai]
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    uvl = bm.loops.layers.uv.verify()
    for face in bm.faces:
        uvs = []
        for loop in face.loops:
            co = loop.vert.co
            major = math.atan2(co[p1], co[p0]) / (2 * math.pi) + 0.5          # around the wheel
            radial = math.hypot(co[p0], co[p1]) - major_radius
            minor = math.atan2(co[ai], radial) / (2 * math.pi) + 0.5          # around the rim tube
            loop[uvl].uv = (major, minor)
            uvs.append((major, minor))
        for comp in (0, 1):                              # seam fix on each wrapped axis
            vals = [uv[comp] for uv in uvs]
            if max(vals) - min(vals) > 0.5:
                for loop in face.loops:
                    if loop[uvl].uv[comp] < 0.5:
                        loop[uvl].uv[comp] += 1.0
    bm.to_mesh(me); bm.free()


def load_img(path, non_color):
    img = bpy.data.images.load(str(path), check_existing=True)
    img.scale(TEX, TEX)
    img.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    return img


def make_material(mat_name, mat_dir, base, sx, sy):
    m = bpy.data.materials.new(mat_name); m.use_nodes = True
    nt = m.node_tree; nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    tc = nodes.new('ShaderNodeTexCoord')
    mp = nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (sx, sy, 1.0)
    links.new(tc.outputs['UV'], mp.inputs['Vector'])

    alb = nodes.new('ShaderNodeTexImage'); alb.image = load_img(mat_dir / f"{base}_albedo.png", False)
    links.new(mp.outputs['Vector'], alb.inputs['Vector'])
    links.new(alb.outputs['Color'], bsdf.inputs['Base Color'])

    mr = nodes.new('ShaderNodeTexImage'); mr.image = load_img(mat_dir / f"{base}_metallic_roughness.png", True)
    links.new(mp.outputs['Vector'], mr.inputs['Vector'])
    sep = nodes.new('ShaderNodeSeparateColor'); links.new(mr.outputs['Color'], sep.inputs['Color'])
    links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
    links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])

    nrm = nodes.new('ShaderNodeTexImage'); nrm.image = load_img(mat_dir / f"{base}_normal.png", True)
    links.new(mp.outputs['Vector'], nrm.inputs['Vector'])
    nm = nodes.new('ShaderNodeNormalMap'); links.new(nrm.outputs['Color'], nm.inputs['Color'])
    links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def unwrap(obj, spec):
    if spec["uw"] == "cyl":
        cylindrical_uv(obj, spec["axis"])
    elif spec["uw"] == "toroidal":
        toroidal_uv(obj, spec["axis"], spec["major"])
    else:
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.object.mode_set(mode='OBJECT')


def skin_single(glb, part):
    sk = SKIN[part]
    mat_name = sk["mat"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.active_object
    unwrap(obj, sk)
    m = make_material(f"{part}_mat", MATS / mat_name, mat_name, sk["sx"], sk["sy"])
    obj.data.materials.clear(); obj.data.materials.append(m)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{part}.glb"), export_format='GLB',
                              use_selection=True)
    print(f"skinned {part} with {mat_name} ({sk['uw']} uv {sk['sx']}x{sk['sy']})")


def skin_split(glb, part):
    """Skin a split part without re-joining: each sub-object gets its own UVs + material,
    role tags re-asserted by node name, hierarchy + extras preserved on export."""
    specs = SPLIT_SKIN[part]
    tags = SPLIT_TAGS.get(part, {})
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    for obj in [o for o in bpy.context.scene.objects if o.type == 'MESH']:
        spec = specs.get(obj.name)
        if spec is None:
            print(f"  warn: no skin spec for {part} sub-object {obj.name!r}; left unskinned")
            continue
        unwrap(obj, spec)
        m = make_material(f"{obj.name}_mat", MATS / spec["mat"], spec["mat"], spec["sx"], spec["sy"])
        obj.data.materials.clear(); obj.data.materials.append(m)
        for k, v in tags.get(obj.name, {}).items():
            obj[k] = v
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{part}.glb"), export_format='GLB',
                              use_selection=True, export_extras=True)
    print(f"skinned split {part}: {len(specs)} pieces")


def main():
    for glb in sorted(IN.glob("*.glb")):
        part = glb.stem
        if ONLY and part not in ONLY:
            continue
        if part in SPLIT_SKIN:
            skin_split(glb, part)
        elif part in SKIN:
            skin_single(glb, part)


if __name__ == "__main__":
    main()
