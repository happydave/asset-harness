"""What a rebuild kept of its source: distances from the source's surface to the rebuilt prop, in
the normalised frame, and the rebuilt prop's own state.

shape_stats.py SRC.glb NORM.json LOW.glb FINISH.json OUT.json

- Source-to-rebuild distance: 20,000 points sampled on the dense source's surface (after the
  normaliser's matrix), each one's distance to the rebuilt prop, as a share of the prop's longest
  side. A thin part the rebuild dropped (a leg, a handle, a frame) shows as a long tail.
- The rebuilt prop: connected pieces, watertight or not, faces whose normal points down into the
  ground plane's half (folds), and the hull's volume over the prop's (when the prop is closed).
"""
import json
import sys

import numpy as np
import trimesh

src, norm, low_path, finish_path, out = sys.argv[1:6]
to_z_up = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
high = trimesh.load(src, force="mesh", process=False)
high.apply_transform(to_z_up)
high.apply_transform(np.array(json.load(open(norm))["matrix"]))
low = trimesh.load(low_path, force="mesh")
low.apply_transform(to_z_up)
size = float(max(high.extents))

pts, _ = trimesh.sample.sample_surface(high, 20000, seed=7)
_, dist, _ = trimesh.proximity.closest_point(low, pts)
rel = dist / size
# pieces and closure on position alone: UV seams and flat normals split vertices, which would count
# every UV island as a piece and no mesh as closed
topo_high = trimesh.Trimesh(high.vertices, high.faces, process=False)
topo_high.merge_vertices(merge_tex=True, merge_norm=True)
topo_low = trimesh.Trimesh(low.vertices, low.faces, process=False)
topo_low.merge_vertices(merge_tex=True, merge_norm=True)
pieces_high = trimesh.graph.connected_components(topo_high.face_adjacency, min_len=50)
pieces_low = topo_low.split(only_watertight=False)
low = topo_low
res = {
    "size": round(size, 4),
    "source_to_rebuild_share_of_size": {
        "median": round(float(np.median(rel)), 4), "p95": round(float(np.percentile(rel, 95)), 4),
        "p99": round(float(np.percentile(rel, 99)), 4), "max": round(float(rel.max()), 4),
        "over_2pct": round(float((rel > 0.02).mean()), 4), "over_5pct": round(float((rel > 0.05).mean()), 4),
    },
    "source_pieces_over_50_faces": len(pieces_high),
    "rebuild_pieces": len(pieces_low),
    "rebuild_watertight": bool(low.is_watertight),
    "rebuild_winding_consistent": bool(low.is_winding_consistent),
    "rebuild_faces": int(len(low.faces)),
}
hull = low.convex_hull
res["hull_volume_over_rebuild"] = round(float(hull.volume / low.volume), 3) if low.is_watertight and low.volume > 0 else None
res["hull_volume_over_box"] = round(float(hull.volume / np.prod(low.extents)), 3)
fin = json.load(open(finish_path))
res["lods"] = [l["tris"] for l in fin["lods"]]
res["hull_tris"] = fin["hull_tris"]
res["gate_pass"] = fin["gate_pass"]
res["gate_failures"] = {k: v["detail"] for k, v in fin["gate"].items() if not v["pass"]}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res))
