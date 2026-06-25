#!/usr/bin/env python3
"""Parametric rover part-mesh catalog for Sounding's `Part` system (WI 608). Runs in Blender
headless on `ai2`:  blender --background --python blender_parts.py -- --out DIR --cell-size 0.5

Geometry is authored parametrically (bpy primitives + modifiers) — image-to-3D is worst at these
revolved/extruded hard-surface solids. Surfaces are embedded PBR material factors for v1 (AI-textured
pbr-materials skinning is a follow-up).

Export contract (read from crates/sim/src/{voxel,rover}.rs):
  - Frame: +Y up, +Z forward, +X lateral (the wheel axle). Steering is about +Y.
  - Origin = the part's mount point (what `Part.mount` positions). Units: metres. glTF Y-up.
  - cell_size-parameterised: all dimensions scale by (cell_size / 0.5).
Each part exports to <out>/<name>.glb plus a manifest.json describing origin/axis/dims.
"""
import bpy, bmesh, sys, json, math
from pathlib import Path

# ---- args after '--' -------------------------------------------------------
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/mk_parts")
CELL = float(argv[argv.index("--cell-size") + 1]) if "--cell-size" in argv else 0.5
S = CELL / 0.5  # scale factor relative to the 0.5 m reference cell
OUT.mkdir(parents=True, exist_ok=True)

# ---- helpers ---------------------------------------------------------------
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(name, rgb, metallic, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    return m

def assign(obj, m):
    obj.data.materials.clear(); obj.data.materials.append(m)

def join(objs):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return bpy.context.active_object

def bevel(obj, width, segs=2):
    md = obj.modifiers.new("bevel", 'BEVEL'); md.width = width * S; md.segments = segs
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=md.name)

def cyl(r, depth, loc=(0, 0, 0), axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(radius=r * S, depth=depth * S, location=tuple(c * S for c in loc))
    o = bpy.context.active_object
    if axis == 'X': o.rotation_euler[1] = math.radians(90)
    elif axis == 'Y': o.rotation_euler[0] = math.radians(90)
    if axis != 'Z':
        bpy.ops.object.transform_apply(rotation=True)
    return o

def box(sx, sy, sz, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c * S for c in loc))
    o = bpy.context.active_object
    o.scale = (sx * S / 2, sy * S / 2, sz * S / 2)
    bpy.ops.object.transform_apply(scale=True)
    return o

def set_origin(obj, loc):
    bpy.context.scene.cursor.location = tuple(c * S for c in loc)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

def export(obj, name):
    for o in bpy.context.scene.objects: o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), export_format='GLB',
                              use_selection=True)
    return len(obj.data.vertices)

# materials (created lazily per part to avoid cross-part leakage on reset)
def m_rubber(): return mat("rubber", (0.04, 0.04, 0.045), 0.0, 0.9)
def m_metal(): return mat("metal", (0.60, 0.62, 0.66), 1.0, 0.35)
def m_metal_dark(): return mat("metal_dark", (0.22, 0.23, 0.26), 1.0, 0.5)
def m_glass(): return mat("solar_glass", (0.04, 0.07, 0.22), 0.2, 0.18)
def m_fabric(): return mat("seat", (0.18, 0.22, 0.28), 0.0, 0.8)

# ---- parts (canonical frame; origin = mount) -------------------------------
# Wheel station components share the hub centre as their mount (origin at axle centre).
def tire():
    o = cyl(0.30, 0.18, axis='X')      # axle along X, disc in YZ, rolls in Z
    bevel(o, 0.05, 2)                   # rounded tread shoulders
    assign(o, m_rubber()); set_origin(o, (0, 0, 0)); return export(o, "tire")

def rim():
    hub = cyl(0.185, 0.16, axis='X')
    boss = cyl(0.06, 0.20, axis='X')   # central boss/axle stub
    o = join([hub, boss]); bevel(o, 0.015, 1)
    assign(o, m_metal()); set_origin(o, (0, 0, 0)); return export(o, "rim")

def suspension():
    # Strut from the axle (origin, y=0) up to the chassis mount (~ride height).
    strut = cyl(0.035, 0.34, loc=(0, 0.17, 0), axis='Y')
    plate = box(0.12, 0.02, 0.12, loc=(0, 0.34, 0))   # top chassis-mount plate
    o = join([strut, plate]); bevel(o, 0.01, 1)
    assign(o, m_metal_dark()); set_origin(o, (0, 0, 0)); return export(o, "suspension")

def seat():
    pad = box(0.34, 0.07, 0.34, loc=(0, 0.20, 0))
    back = box(0.34, 0.34, 0.07, loc=(0, 0.37, -0.14))   # backrest toward -Z (faces +Z)
    o = join([pad, back]); bevel(o, 0.02, 1)
    assign(o, m_fabric()); set_origin(o, (0, 0, 0)); return export(o, "seat")

def antenna():
    base = cyl(0.05, 0.04, loc=(0, 0.02, 0), axis='Y')
    mast = cyl(0.012, 0.55, loc=(0, 0.30, 0), axis='Y')
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025 * S, location=(0, 0.57 * S, 0))
    tip = bpy.context.active_object
    o = join([base, mast, tip])
    assign(o, m_metal()); set_origin(o, (0, 0, 0)); return export(o, "antenna")

def solar_panel():
    glass = box(0.70, 0.02, 0.46, loc=(0, 0.05, 0))     # panel in XZ, normal +Y
    frame = box(0.74, 0.04, 0.50, loc=(0, 0.035, 0))
    stem = cyl(0.02, 0.05, loc=(0, 0.015, 0), axis='Y')
    o = join([glass, frame, stem])
    assign(o, m_glass()); set_origin(o, (0, 0, 0)); return export(o, "solar_panel")

def bumper():
    o = box(0.72, 0.10, 0.12, loc=(0, 0, 0.04))         # long axis X, front +Z
    bevel(o, 0.03, 2)
    assign(o, m_metal_dark()); set_origin(o, (0, 0, 0)); return export(o, "bumper")

PARTS = {
    "tire": ("rubber", "hub centre", "+X axle; disc in YZ (rolls +Z)", tire),
    "rim": ("metal", "hub centre", "+X axle", rim),
    "suspension": ("metal_dark", "axle (bottom)", "strut along +Y to chassis plate", suspension),
    "seat": ("fabric", "base centre", "faces +Z, up +Y", seat),
    "antenna": ("metal", "base", "mast along +Y", antenna),
    "solar_panel": ("solar_glass", "base centre", "panel in XZ, normal +Y", solar_panel),
    "bumper": ("metal_dark", "mount centre", "long axis +X, front +Z", bumper),
}


def main():
    manifest = {"frame": "+Y up, +Z forward, +X lateral(axle); metres; glTF Y-up",
                "cell_size": CELL, "reference_cell": 0.5, "parts": {}}
    for name, (material, origin, axis, fn) in PARTS.items():
        reset()
        verts = fn()
        manifest["parts"][name] = {"file": f"{name}.glb", "material": material,
                                   "origin": origin, "orientation": axis, "verts": verts}
        print(f"built {name}: {verts} verts -> {name}.glb")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("manifest ->", OUT / "manifest.json")


if __name__ == "__main__":
    main()
