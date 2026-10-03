"""Source-to-rebuild distance without the source's internal surfaces. outside.py OUTDIR NAME...

TRELLIS.2 leaves surfaces inside its meshes where parts meet (between stacked books, under a chest's
lid). A closed rebuild drops them, and shape_stats.py's distance counts them as lost. Here a source
point inside a closed rebuild and deeper than 2 % of the size is left out; an open rebuild keeps
every point. Writes OUTDIR/NAME/outside.json.
"""
import json
import sys

import numpy as np
import trimesh

out, names = sys.argv[1], sys.argv[2:]
to_z_up = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
for s in names:
    high = trimesh.load(f"src/{s}.glb", force="mesh", process=False)
    high.apply_transform(to_z_up)
    high.apply_transform(np.array(json.load(open(f"{out}/{s}/norm.json"))["matrix"]))
    low = trimesh.load(f"{out}/{s}/final/{s}_lod0.glb", force="mesh")
    low.apply_transform(to_z_up)
    size = float(max(high.extents))
    pts, _ = trimesh.sample.sample_surface(high, 20000, seed=7)
    _, d, _ = trimesh.proximity.closest_point(low, pts)
    d /= size
    welded = low.copy()
    welded.merge_vertices(merge_tex=True, merge_norm=True)
    buried = (welded.contains(pts) & (d > 0.02)) if welded.is_watertight else np.zeros(len(pts), bool)
    keep = ~buried
    r = {"buried_share": float(buried.mean()),
         "rule": "source points inside a closed rebuild and deeper than 2 % of the size are dropped as internal surfaces",
         "p95": float(np.percentile(d[keep], 95)), "max": float(d[keep].max())}
    json.dump(r, open(f"{out}/{s}/outside.json", "w"), indent=1)
    print(s, f"buried {r['buried_share'] * 100:.1f} %", f"p95 {r['p95'] * 100:.1f} %", f"max {r['max'] * 100:.1f} %")
