"""Stand a prop upright by its generator's rule, put its footprint's sides on the axes and its foot at
z 0, and scale it by its category's governing axis.

TRELLIS.2 writes props upright, so its up is kept. The stable resting pose is measured and reported, never
applied: it lays a chair on its back and turns a bench or barrel over.
"""
import numpy as np
import trimesh

from common import GENERATORS


def _angle(m):
    return float(np.degrees(np.arccos(np.clip((np.trace(m) - 1) / 2, -1, 1))))


def normalise(mesh, generator, governing, size):
    """mesh: the source in the z-up frame. Returns the 4x4 matrix and what was found."""
    if GENERATORS.get(generator) != "source":
        raise ValueError(f"unsupported generator {generator}")
    hull = mesh.convex_hull
    poses, probs = trimesh.poses.compute_stable_poses(hull, n_samples=1)
    best = poses[int(np.argmax(probs))]
    up_in_source = best[:3, :3].T @ np.array([0, 0, 1.0])
    tilt = float(np.degrees(np.arccos(np.clip(up_in_source[2], -1, 1))))

    yaw_tf, _ = trimesh.bounds.oriented_bounds_2D(hull.vertices[:, :2])
    rot = np.eye(4)
    rot[:2, :2] = yaw_tf[:2, :2]
    placed = hull.copy()
    placed.apply_transform(rot)
    lo, hi = placed.bounds
    ext = hi - lo
    if governing == "horizontal":
        scale = size / max(ext[0], ext[1])
    elif governing == "height":
        scale = size / ext[2]
    else:
        raise ValueError(f"unknown governing axis {governing}")
    centre = np.eye(4)
    centre[:3, 3] = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]
    total = np.diag([scale, scale, scale, 1.0]) @ centre @ rot
    final = hull.copy()
    final.apply_transform(total)
    return {
        "generator": generator,
        "up_rule": GENERATORS[generator],
        "matrix": total.tolist(),
        "stable_pose_tilt_deg": round(tilt, 2),
        "yaw_deg": round(_angle(rot[:3, :3]), 2),
        "governing_axis": governing,
        "scale": round(float(scale), 6),
        "extents_after": [round(float(v), 4) for v in final.extents],
    }
