"""Normalise a generated prop: work out the rotation, ground and scale that stand it upright, its
sides on the axes, its foot at z 0 and its longest horizontal side at the category's length.

Frame: Blender's (z up), into which Blender's glTF importer brings a glb (x, -z, y of the file).
Writes the 4x4 matrix and what it found as JSON. Usage: normalise.py IN.glb LONGEST OUT.json [--up stable|source]

--up stable (the default, WI 2091): upright is the most probable resting pose. --up source: the file's
own up is kept (TRELLIS.2 writes its props upright; the stable pose lays a chair on its back and turns
a bench or barrel over, WI 2112), and only the turn about it, the ground and the scale are found. The
stable pose's reading is reported either way.
"""
import json
import sys

import numpy as np
import trimesh

src, longest, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
up_mode = sys.argv[sys.argv.index("--up") + 1] if "--up" in sys.argv else "stable"
mesh = trimesh.load(src, force="mesh")
# glTF (y up) to Blender (z up): x, -z, y
to_z_up = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
mesh.apply_transform(to_z_up)
hull = mesh.convex_hull

# Upright: the most probable resting pose on a plane.
poses, probs = trimesh.poses.compute_stable_poses(hull, n_samples=1)
order = np.argsort(probs)[::-1]
stable_rest = poses[order[0]]
up_axis = stable_rest[:3, :3].T @ np.array([0, 0, 1.0])  # the source's direction the stable pose makes z
rest = stable_rest if up_mode == "stable" else np.eye(4)

# Sides on the axes: the minimum-area rectangle of the footprint after the rest pose.
rested = hull.copy()
rested.apply_transform(rest)
xy = rested.vertices[:, :2]
yaw_tf, rect = trimesh.bounds.oriented_bounds_2D(xy)
yaw = np.eye(4)
yaw[:2, :2] = yaw_tf[:2, :2]
rot = yaw @ rest
rot[:3, 3] = 0

placed = hull.copy()
placed.apply_transform(rot)
lo, hi = placed.bounds
ext = hi - lo
scale = longest / max(ext[0], ext[1])
centre = np.eye(4)
centre[:3, 3] = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]
s = np.diag([scale, scale, scale, 1.0])
total = s @ centre @ rot

# The rotation's angle from identity, and from the nearest quarter turn about z (a box's symmetry).
r3 = rot[:3, :3]
def angle(m):
    return float(np.degrees(np.arccos(np.clip((np.trace(m) - 1) / 2, -1, 1))))
quarter = min(angle(np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]).T @ r3)
              for a in np.radians([0, 90, 180, 270]))
# signed: a prop the stable pose turns over reads 180, not 0
up_tilt = float(np.degrees(np.arccos(np.clip(up_axis[2], -1, 1))))

final = hull.copy()
final.apply_transform(total)
res = {
    "source": src,
    "up_mode": up_mode,
    "faces": int(len(mesh.faces)),
    "matrix": total.tolist(),
    "rest_probability": float(probs[order[0]]),
    "poses_considered": int(len(probs)),
    "stable_pose_up_in_source": up_axis.round(4).tolist(),
    "stable_pose_tilt_deg": round(up_tilt, 2),
    "rotation_deg": round(angle(r3), 2),
    "rotation_from_nearest_quarter_turn_deg": round(quarter, 2),
    "scale": round(float(scale), 5),
    "extents_after": [round(float(v), 4) for v in final.extents],
}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "matrix"}, indent=1))
