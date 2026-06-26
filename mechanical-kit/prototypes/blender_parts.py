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
ONLY = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None  # subset of part names
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

def cone(r1, r2, depth, loc=(0, 0, 0), axis='Z'):
    # r1 = base radius (toward -axis), r2 = top radius (toward +axis). For Y/X, +Z maps to +axis.
    bpy.ops.mesh.primitive_cone_add(radius1=r1 * S, radius2=r2 * S, depth=depth * S,
                                    location=tuple(c * S for c in loc))
    o = bpy.context.active_object
    if axis == 'X': o.rotation_euler[1] = math.radians(-90)
    elif axis == 'Y': o.rotation_euler[0] = math.radians(-90)
    if axis != 'Z':
        bpy.ops.object.transform_apply(rotation=True)
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

# Split-part support (WI 666): export a part as a named, tagged node hierarchy under an
# Empty root at the mount origin, instead of one joined mesh. Role tags ride in node
# `extras` (Blender custom props + export_extras). SUBPARTS records them for the manifest.
SUBPARTS = {}

def new_empty(name):
    e = bpy.data.objects.new(name, None)            # None data → Empty
    bpy.context.scene.collection.objects.link(e)
    e.location = (0, 0, 0)
    return e

def export_group(name, subparts):
    """subparts: list of (obj, node_name, role_props). Parents each under an Empty named
    `name` at the origin (identity → world transform preserved), tags it, and exports."""
    root = new_empty(name)
    for obj, node_name, props in subparts:
        obj.name = node_name
        for k, v in props.items():
            obj[k] = v
        obj.parent = root
    for o in bpy.context.scene.objects: o.select_set(False)
    root.select_set(True)
    for obj, _, _ in subparts: obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), export_format='GLB',
                              use_selection=True, export_extras=True)
    SUBPARTS[name] = [{"node": n, **props} for (_, n, props) in subparts]
    return sum(len(obj.data.vertices) for obj, _, _ in subparts)

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

# --- drivetrain / power (WI 653) ---
def m_motor(): return mat("motor", (0.18, 0.19, 0.22), 1.0, 0.45)
def m_battery(): return mat("battery", (0.10, 0.12, 0.14), 0.2, 0.55)

def motor():
    # Electric drive motor: a finned can on the +X axle with an output shaft toward the wheel and a
    # terminal box on top. Origin at the body centre (the axle-line mount).
    body = cyl(0.11, 0.26, axis='X')
    fins = [cyl(0.125, 0.015, loc=(x, 0, 0), axis='X') for x in (-0.08, -0.03, 0.02, 0.07)]
    shaft = cyl(0.028, 0.12, loc=(0.19, 0, 0), axis='X')   # output shaft toward +X (the wheel)
    term = box(0.09, 0.06, 0.13, loc=(0, 0.12, 0))         # terminal box on top (+Y)
    o = join([body] + fins + [shaft, term]); bevel(o, 0.006, 1)
    assign(o, m_motor()); set_origin(o, (0, 0, 0)); return export(o, "motor")

def battery():
    # Battery pack: plastic body + lid, two metal terminals. Exported as a tagged hierarchy
    # (split part, WI 666) rather than one joined mesh. Origin at base centre = the mount.
    plastic, metal = m_battery(), m_metal()
    body = box(0.30, 0.20, 0.22, loc=(0, 0.10, 0)); bevel(body, 0.008, 1); assign(body, plastic)
    lid = box(0.32, 0.03, 0.24, loc=(0, 0.205, 0)); bevel(lid, 0.008, 1); assign(lid, plastic)
    t1 = cyl(0.022, 0.05, loc=(-0.09, 0.235, 0), axis='Y'); bevel(t1, 0.004, 1); assign(t1, metal)
    t2 = cyl(0.022, 0.05, loc=(0.09, 0.235, 0), axis='Y'); bevel(t2, 0.004, 1); assign(t2, metal)
    return export_group("battery", [
        (body, "battery_body", {"role": "body"}),
        (lid, "battery_lid", {"role": "lid"}),
        (t1, "battery_terminal_pos", {"role": "terminal", "polarity": "positive"}),
        (t2, "battery_terminal_neg", {"role": "terminal", "polarity": "negative"}),
    ])

# --- variants / additions ---
def m_leather_light(): return mat("leather_light", (0.62, 0.52, 0.38), 0.0, 0.55)

def seat_leather():
    pad = box(0.34, 0.07, 0.34, loc=(0, 0.20, 0))
    back = box(0.34, 0.34, 0.07, loc=(0, 0.37, -0.14))
    o = join([pad, back]); bevel(o, 0.02, 1)
    assign(o, m_leather_light()); set_origin(o, (0, 0, 0)); return export(o, "seat_leather")

def solar_panel_2x1():   # same panel geometry; 2x1 cell material applied in the texture pass
    glass = box(0.70, 0.02, 0.46, loc=(0, 0.05, 0))
    frame = box(0.74, 0.04, 0.50, loc=(0, 0.035, 0))
    stem = cyl(0.02, 0.05, loc=(0, 0.015, 0), axis='Y')
    o = join([glass, frame, stem])
    assign(o, m_glass()); set_origin(o, (0, 0, 0)); return export(o, "solar_panel_2x1")

def steering_wheel():
    # Rim torus in the XY plane (faces +Z, the driver) + hub + 3 radial spokes; origin at hub centre
    # (the column mount). Leather wrap (toroidal unwrap) is applied in the texture pass.
    bpy.ops.mesh.primitive_torus_add(major_radius=0.18 * S, minor_radius=0.018 * S, location=(0, 0, 0),
                                     major_segments=48, minor_segments=12)
    rim = bpy.context.active_object
    hub = cyl(0.045, 0.05, axis='Z')
    spokes = []
    for deg in (90, 210, 330):
        a = math.radians(deg)
        sp = box(0.16, 0.022, 0.022, loc=(0.11 * math.cos(a), 0.11 * math.sin(a), 0))
        sp.rotation_euler[2] = a                       # spin in place to point radially
        bpy.ops.object.transform_apply(rotation=True)
        spokes.append(sp)
    o = join([rim, hub] + spokes)
    assign(o, m_leather_light()); set_origin(o, (0, 0, 0)); return export(o, "steering_wheel")

# --- rocket-domain catalog + fittings ---
def m_white(): return mat("white_hull", (0.85, 0.86, 0.88), 0.1, 0.4)
def m_heat(): return mat("heat_metal", (0.35, 0.33, 0.30), 0.9, 0.45)
def m_screen(): return mat("screen", (0.02, 0.03, 0.05), 0.1, 0.15)

# Axial rocket parts stack along +Y (rocket "up"); origin at the bottom mount plane unless noted.
def fuel_tank():
    o = cyl(0.25, 0.78, loc=(0, 0.39, 0), axis='Y'); bevel(o, 0.02, 1)
    assign(o, m_white()); set_origin(o, (0, 0, 0)); return export(o, "fuel_tank")

def nose_cone():
    o = cone(0.25, 0.0, 0.46, loc=(0, 0.23, 0), axis='Y')   # base down at y=0, tip up
    assign(o, m_white()); set_origin(o, (0, 0, 0)); return export(o, "nose_cone")

def engine_bell():
    o = cone(0.22, 0.06, 0.30, loc=(0, -0.15, 0), axis='Y')  # throat(top,+Y) at y=0, exit flares below
    assign(o, m_heat()); set_origin(o, (0, 0, 0)); return export(o, "engine_bell")

def decoupler():
    o = cyl(0.27, 0.08, loc=(0, 0.04, 0), axis='Y'); bevel(o, 0.01, 1)
    assign(o, m_metal_dark()); set_origin(o, (0, 0, 0)); return export(o, "decoupler")

def fin():
    o = box(0.22, 0.30, 0.02, loc=(0.11, 0.15, 0))   # root at x=0, blade +X, up +Y, thin Z
    bevel(o, 0.05, 1)
    assign(o, m_metal()); set_origin(o, (0, 0, 0)); return export(o, "fin")

# Wall fittings face +Z (outward); origin at the hull-mount centre.
def hatch_round():
    disc = cyl(0.17, 0.04, axis='Z')
    bpy.ops.mesh.primitive_torus_add(major_radius=0.18 * S, minor_radius=0.02 * S, location=(0, 0, 0),
                                     major_segments=32, minor_segments=8)
    rim = bpy.context.active_object
    handle = box(0.12, 0.03, 0.03, loc=(0, 0, 0.04))
    o = join([disc, rim, handle]); assign(o, m_metal()); set_origin(o, (0, 0, 0)); return export(o, "hatch_round")

def hatch_rect():
    panel = box(0.30, 0.40, 0.04, loc=(0, 0, 0.01))
    frame = box(0.34, 0.44, 0.02, loc=(0, 0, -0.01))
    handle = box(0.04, 0.12, 0.03, loc=(0.10, 0, 0.05))
    o = join([panel, frame, handle]); bevel(o, 0.01, 1)
    assign(o, m_metal()); set_origin(o, (0, 0, 0)); return export(o, "hatch_rect")

def _dish(r, name):
    refl = cone(r * 0.35, r, r * 0.4, loc=(0, 0, 0), axis='Z')   # wide opening toward +Z
    stem = cyl(0.02, 0.18, loc=(0, 0, -0.12), axis='Z')
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03 * S, location=(0, 0, r * 0.4 * S))
    feed = bpy.context.active_object
    o = join([refl, stem, feed]); assign(o, m_white()); set_origin(o, (0, 0, -0.21))
    return export(o, name)

def dish_small(): return _dish(0.15, "dish_small")
def dish_large(): return _dish(0.35, "dish_large")

def tablet():
    o = box(0.16, 0.24, 0.012, loc=(0, 0, 0)); bevel(o, 0.006, 2)   # flat slab, screen faces +Z
    assign(o, m_screen()); set_origin(o, (0, 0, 0)); return export(o, "tablet")

PARTS = {
    "tire": ("rubber", "hub centre", "+X axle; disc in YZ (rolls +Z)", tire),
    "rim": ("metal", "hub centre", "+X axle", rim),
    "suspension": ("metal_dark", "axle (bottom)", "strut along +Y to chassis plate", suspension),
    "seat": ("fabric", "base centre", "faces +Z, up +Y", seat),
    "antenna": ("metal", "base", "mast along +Y", antenna),
    "solar_panel": ("solar_glass", "base centre", "panel in XZ, normal +Y", solar_panel),
    "bumper": ("metal_dark", "mount centre", "long axis +X, front +Z", bumper),
    "motor": ("metal", "body centre (axle)", "+X axle; output shaft +X to wheel", motor),
    "battery": ("battery", "base centre", "upright box; terminals up +Y", battery),
    "seat_leather": ("leather_light", "base centre", "faces +Z, up +Y", seat_leather),
    "solar_panel_2x1": ("solar_glass", "base centre", "panel in XZ, normal +Y", solar_panel_2x1),
    "steering_wheel": ("leather_light", "hub centre (column mount)", "rim in XY, faces +Z", steering_wheel),
    "fuel_tank": ("white_hull", "bottom centre", "axis +Y; stacks up", fuel_tank),
    "nose_cone": ("white_hull", "base centre", "axis +Y; tip up", nose_cone),
    "engine_bell": ("heat_metal", "throat (top) centre", "axis +Y; exit flares down -Y", engine_bell),
    "decoupler": ("metal_dark", "bottom centre", "axis +Y; inter-stage band", decoupler),
    "fin": ("metal", "inner-bottom root", "blade +X, up +Y, thin Z", fin),
    "hatch_round": ("metal", "hull-mount centre", "disc in XY, faces +Z", hatch_round),
    "hatch_rect": ("metal", "hull-mount centre", "panel in XY, faces +Z", hatch_rect),
    "dish_small": ("white_hull", "back mount centre", "opens +Z", dish_small),
    "dish_large": ("white_hull", "back mount centre", "opens +Z", dish_large),
    "tablet": ("screen", "back centre", "screen faces +Z", tablet),
}


def main():
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {
        "frame": "+Y up, +Z forward, +X lateral(axle); metres; glTF Y-up",
        "cell_size": CELL, "reference_cell": 0.5, "parts": {}}
    for name, (material, origin, axis, fn) in PARTS.items():
        if ONLY and name not in ONLY:
            continue
        reset()
        verts = fn()
        manifest["parts"][name] = {"file": f"{name}.glb", "material": material,
                                   "origin": origin, "orientation": axis, "verts": verts}
        if name in SUBPARTS:
            manifest["parts"][name]["subparts"] = SUBPARTS[name]
        print(f"built {name}: {verts} verts -> {name}.glb")
    mpath.write_text(json.dumps(manifest, indent=2))
    print("manifest ->", mpath)


if __name__ == "__main__":
    main()
