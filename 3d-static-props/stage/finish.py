"""LODs, collision and glTF validation for an arm's LOD0."""
import json
import os
import subprocess

import numpy as np
import trimesh

from common import TO_Y_UP, TO_Z_UP, welded
from parts import collision_boxes, obb_box
from simplify import simplify

HULL_RATIO = 1.5  # the organic class keeps a hull up to this many times the rebuild's volume


def lods(lod0_path, outdir, stem):
    """LOD1 and LOD2 at about a half and a quarter of LOD0, by the attribute-aware simplifier (positions
    and UVs), falling back to the sloppy one when it stops short."""
    lod0 = trimesh.load(lod0_path, force="mesh", process=False)
    # flat shading splits every vertex per face, which makes every edge a seam the simplifier will not
    # collapse: weld vertices that share a position and a UV (normals are not carried into the LODs)
    w = lod0.copy()
    w.merge_vertices(merge_norm=True, merge_tex=False)
    rows = []
    for k, frac, max_error in ((1, 0.5, 0.05), (2, 0.25, 0.2)):
        faces, how, err = simplify(w.vertices, w.faces, int(len(lod0.faces) * frac), max_error, uv=w.visual.uv)
        m = trimesh.Trimesh(vertices=w.vertices, faces=faces, process=False,
                            visual=trimesh.visual.TextureVisuals(uv=w.visual.uv, material=w.visual.material))
        m.remove_unreferenced_vertices()
        path = os.path.join(outdir, f"{stem}_lod{k}.glb")
        m.export(path)
        rows.append({"file": path, "tris": int(len(m.faces)), "simplifier": how, "relative_error": round(err, 4)})
    return rows


def collision(kind, lod0_zup, source_w, source_parts):
    """The collision mesh in the z-up frame, and the kind actually used."""
    if kind == "box":
        return obb_box(lod0_zup), "box"
    if kind == "part_boxes":
        return collision_boxes(source_w, source_parts), "part_boxes"
    hull = lod0_zup.convex_hull
    if kind == "hull":
        return hull, "hull"
    if kind == "hull_or_part_boxes":
        w = welded(lod0_zup)
        if w.is_watertight and w.volume > 0 and hull.volume <= HULL_RATIO * w.volume:
            return hull, "hull"
        return collision_boxes(source_w, source_parts), "part_boxes"
    raise ValueError(f"unknown collision kind {kind}")


def write_collision(mesh_zup, path):
    """Vertices and triangles in the glb's own frame (y up), with the bounds."""
    m = mesh_zup.copy()
    m.apply_transform(TO_Y_UP)
    lo, hi = m.bounds
    with open(path, "w") as f:
        json.dump({"frame": "glb (y up), yards", "bounds": {"min": lo.round(5).tolist(), "max": hi.round(5).tolist()},
                   "vertices": m.vertices.round(5).tolist(), "triangles": m.faces.reshape(-1).tolist()}, f)


def validate(paths, validator):
    """glTF-Validator over each file. A validator that cannot run fails the row."""
    rows = {}
    for p in paths:
        name = f"gltf_validator {os.path.basename(p)}"
        try:
            r = subprocess.run([validator, "-o", p], capture_output=True, text=True, timeout=120)
            issues = json.loads(r.stdout)["issues"]
            rows[name] = (issues["numErrors"] == 0, f"errors {issues['numErrors']} warnings {issues['numWarnings']}")
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
            rows[name] = (False, f"validator did not run: {type(e).__name__}: {e}")
    return rows


def load_zup(path):
    m = trimesh.load(path, force="mesh", process=False)
    m.apply_transform(TO_Z_UP)
    return m
