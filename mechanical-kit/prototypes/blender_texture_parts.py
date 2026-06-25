#!/usr/bin/env python3
"""Skin the v1 rover parts with AI PBR materials (the "AI surface" half of mechanical-kit). Headless
on `ai2`:  blender --background --python blender_texture_parts.py -- --in DIR --materials DIR --out DIR

Per part: import the v1 glb (geometry/orientation/origin already correct), smart-UV-unwrap, bind a
Principled material from the pbr-materials map set (albedo + tangent normal + packed metallic-
roughness, Bevy convention G=rough/B=metal), tile via a Mapping scale, and re-export a textured glb.
Embedded textures are downscaled to 256 px (parts are small) to keep glbs lean.
"""
import bpy, sys, math
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(flag, default): return argv[argv.index(flag) + 1] if flag in argv else default
IN = Path(arg("--in", "/tmp/mk_parts"))
MATS = Path(arg("--materials", "/tmp/mk_materials"))
OUT = Path(arg("--out", "/tmp/mk_parts_tex")); OUT.mkdir(parents=True, exist_ok=True)
TEX = 256  # embedded texture size

# part -> (material set, UV tiling scale)
SKIN = {
    "tire": ("rubber", 4.0), "rim": ("metal_panel", 3.0), "suspension": ("metal_panel", 3.0),
    "seat": ("seat_fabric", 2.0), "antenna": ("metal_panel", 2.0),
    "solar_panel": ("solar_cells", 2.0), "bumper": ("metal_panel", 3.0),
}


def load_img(path, non_color):
    img = bpy.data.images.load(str(path), check_existing=True)
    img.scale(TEX, TEX)
    img.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    return img


def make_material(mat_name, mat_dir, base, scale):
    m = bpy.data.materials.new(mat_name); m.use_nodes = True
    nt = m.node_tree; nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    tc = nodes.new('ShaderNodeTexCoord')
    mp = nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (scale, scale, scale)
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


def main():
    for glb in sorted(IN.glob("*.glb")):
        part = glb.stem
        if part not in SKIN:
            continue
        mat_name, scale = SKIN[part]
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

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.object.mode_set(mode='OBJECT')

        m = make_material(f"{part}_mat", MATS / mat_name, mat_name, scale)
        obj.data.materials.clear(); obj.data.materials.append(m)

        bpy.ops.export_scene.gltf(filepath=str(OUT / f"{part}.glb"), export_format='GLB',
                                  use_selection=True)
        print(f"skinned {part} with {mat_name} (uv x{scale})")


if __name__ == "__main__":
    main()
