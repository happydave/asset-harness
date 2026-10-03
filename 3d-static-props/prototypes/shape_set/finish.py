"""LODs, collision, the sidecar's numbers and the budget gate for a rebuilt prop.

finish.py LOD0.glb OUTDIR BUDGET TEXMAX LONGEST

LODs by meshoptimizer's attribute-aware simplifier (positions and UVs) at a half and a quarter of
LOD0, the last falling back to the sloppy simplifier if the first stops short. Collision is the
convex hull of LOD0. Everything the test world's sidecar needs is written in the world's axes
(x, y, z = the glb's z, x, y; yards). The gate refuses a prop over its budget, a texture over its
largest side, a foot off the ground, a size off its category's, or a missing collision mesh.
"""
import json
import os
import subprocess
import sys

import meshoptimizer as mo
import numpy as np
import trimesh

src, outdir, budget, texmax, longest = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
os.makedirs(outdir, exist_ok=True)
lod0 = trimesh.load(src, force="mesh", process=False)
stem = os.environ.get("REBUILD_STEM", "crate")
res = {"lod0": src, "lods": []}


def simplify(mesh, target_tris, max_error):
    pos = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    uv = np.ascontiguousarray(mesh.visual.uv, dtype=np.float32)
    idx = np.ascontiguousarray(mesh.faces.reshape(-1), dtype=np.uint32)
    dst = np.zeros_like(idx)
    # the binding (0.2.30a0) passes Python floats where its library wants C floats and fails, so
    # the library's functions are called directly
    from meshoptimizer.simplifier import lib
    import ctypes as C
    F, U = C.POINTER(C.c_float), C.POINTER(C.c_uint)
    w = np.array([0.5, 0.5], dtype=np.float32)
    err = C.c_float(0)
    n = lib.meshopt_simplifyWithAttributes(dst.ctypes.data_as(U), idx.ctypes.data_as(U), C.c_size_t(len(idx)),
                                           pos.ctypes.data_as(F), C.c_size_t(len(pos)), C.c_size_t(12),
                                           uv.ctypes.data_as(F), C.c_size_t(8), w.ctypes.data_as(F), C.c_size_t(2),
                                           C.POINTER(C.c_ubyte)(), C.c_size_t(target_tris * 3), C.c_float(max_error),
                                           C.c_uint(0), C.byref(err))
    how = "attributes"
    if n > target_tris * 3 * 1.25:
        alt = np.zeros_like(idx)
        alt_err = C.c_float(0)
        m = lib.meshopt_simplifySloppy(alt.ctypes.data_as(U), idx.ctypes.data_as(U), C.c_size_t(len(idx)),
                                       pos.ctypes.data_as(F), C.c_size_t(len(pos)), C.c_size_t(12),
                                       C.c_size_t(target_tris * 3), C.c_float(max_error), C.byref(alt_err))
        how = f"attributes (stopped at {n // 3})"
        if m < n:  # the sloppy simplifier ignores UV seams; kept only when it gets nearer the target
            dst, n, err, how = alt, m, alt_err, f"sloppy (attributes stopped at {n // 3})"
    err = np.array([err.value])
    faces = dst[:n].reshape(-1, 3)
    out = trimesh.Trimesh(vertices=mesh.vertices, faces=faces, visual=trimesh.visual.TextureVisuals(uv=mesh.visual.uv, material=mesh.visual.material), process=False)
    out.remove_unreferenced_vertices()
    return out, how, float(err[0])


# flat shading splits every vertex per face, which makes every edge a seam the simplifier will not
# collapse: weld vertices that share a position and a UV (normals are not carried into the LODs)
welded = lod0.copy()
welded.merge_vertices(merge_norm=True, merge_tex=False)
res["lod0_vertices"], res["welded_vertices"] = int(len(lod0.vertices)), int(len(welded.vertices))
# the error a level may reach, as a share of the prop's extent: the last level is seen only far off
for k, frac, max_error in ((1, 0.5, 0.05), (2, 0.25, 0.2)):
    m, how, err = simplify(welded, int(len(lod0.faces) * frac), max_error)
    path = os.path.join(outdir, f"{stem}_lod{k}.glb")
    m.export(path)
    res["lods"].append({"file": path, "tris": int(len(m.faces)), "simplifier": how, "relative_error": round(err, 4)})

lod0_path = os.path.join(outdir, f"{stem}_lod0.glb")
with open(src, "rb") as f, open(lod0_path, "wb") as g:
    g.write(f.read())


def world(v):  # glb (y up) to the world's axes: x, y, z = glb z, x, y
    v = np.asarray(v)
    return np.stack([v[:, 2], v[:, 0], v[:, 1]], axis=1)


hull = lod0.convex_hull
box = trimesh.creation.box(extents=lod0.extents, transform=trimesh.transformations.translation_matrix(lod0.bounds.mean(axis=0)))
vw = world(lod0.vertices)
lo, hi = vw.min(axis=0), vw.max(axis=0)
coll = {
    "bounds": {"min": lo.round(5).tolist(), "max": hi.round(5).tolist()},
    "bounds_radius": round(float(np.linalg.norm(hi - lo) / 2), 5),
    "collision": {
        "vertices": world(hull.vertices).round(5).tolist(),
        # the axis change is a cyclic permutation (a rotation), so the hull's outward winding holds
        "triangles": hull.faces.reshape(-1).tolist(),
    },
}
json.dump(coll, open(os.path.join(outdir, f"{stem}.collision.json"), "w"))
res["hull_tris"] = int(len(hull.faces))
res["hull_volume_over_mesh"] = round(float(hull.volume / max(lod0.convex_hull.volume, 1e-9)), 3)
res["box_tris_alternative"] = int(len(box.faces))
res["size_world"] = (hi - lo).round(4).tolist()

# the budget gate
tex = lod0.visual.material.baseColorTexture.size
checks = {
    "triangles": (len(lod0.faces) <= budget, f"{len(lod0.faces)} <= {budget}"),
    "lods_decrease": (all(l["tris"] < len(lod0.faces) for l in res["lods"]) and res["lods"][1]["tris"] < res["lods"][0]["tris"], [l["tris"] for l in res["lods"]]),
    "texture": (max(tex) <= texmax, f"{tex} <= {texmax}"),
    "foot_on_ground": (abs(lo[2]) <= 0.01, f"min z {lo[2]:.4f}"),
    "category_size": (abs(max(hi[0] - lo[0], hi[1] - lo[1]) - longest) <= 0.1 * longest, f"longest side {max(hi[0] - lo[0], hi[1] - lo[1]):.3f} vs {longest}"),
    "collision": (len(hull.faces) > 0 and hull.is_watertight, f"{len(hull.faces)} triangles, watertight {hull.is_watertight}"),
}
validator = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "gltf_validator")
for p in [lod0_path] + [l["file"] for l in res["lods"]]:
    r = subprocess.run([validator, "-o", p], capture_output=True, text=True)
    rep = json.loads(r.stdout)
    issues = rep["issues"]
    checks[f"gltf_validator {os.path.basename(p)}"] = (issues["numErrors"] == 0, f"errors {issues['numErrors']} warnings {issues['numWarnings']} infos {issues['numInfos']}")
res["gate"] = {k: {"pass": bool(v[0]), "detail": v[1]} for k, v in checks.items()}
res["gate_pass"] = all(v[0] for v in checks.values())
json.dump(res, open(os.path.join(outdir, "finish.json"), "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
sys.exit(0 if res["gate_pass"] else 1)
