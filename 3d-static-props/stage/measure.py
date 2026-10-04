"""What a rebuild kept of its source, measured in the normalised z-up frame."""
import numpy as np
import trimesh
from PIL import Image

from common import welded

CONTACT = 0.01   # a piece within this share of the size of another piece or the ground is not floating
BURIED = 0.02    # source points inside a closed rebuild and deeper than this are internal surfaces


def pieces(lod0):
    return welded(lod0).split(only_watertight=False)


def merged_pieces(lod0, size):
    """The rebuild's pieces counted as the source's parts are: welded components merged where they lie
    within the contact distance, every piece counted (no area floor, so a loose crumb still counts)."""
    from parts import source_parts
    return source_parts(lod0, size, area_floor=0.0)[2]["parts"]


def floating(lod0, size, contact=CONTACT):
    """Pieces further than `contact` of the size from every other piece and from the ground, each with
    its gaps. Also returns the merged piece count (merged_pieces)."""
    parts = pieces(lod0)
    rows = []
    for i, p in enumerate(parts):
        ground = float(p.bounds[0][2])
        others = [q for j, q in enumerate(parts) if j != i]
        if others:
            pts = np.vstack([p.vertices, trimesh.sample.sample_surface(p, 400, seed=3)[0]])
            _, d, _ = trimesh.proximity.closest_point(trimesh.util.concatenate(others), pts)
            near = float(d.min())
        else:
            near = float("inf")
        if ground > contact * size and near > contact * size:
            rows.append({"piece": i, "faces": int(len(p.faces)), "ground_gap": round(ground / size, 4),
                         "nearest_piece": round(near / size, 4) if np.isfinite(near) else None})
    return rows, merged_pieces(lod0, size)


def shape_p95(source_w, lod0, size, n=20000):
    """The shape's distance at p95 as a share of the size, the larger of two directions:
    - source to rebuild, leaving out source points inside a closed piece of the rebuild and deeper than
      BURIED: TRELLIS.2 leaves surfaces where parts meet and inside bodies, which a closed piece rightly
      drops. A piece counts on its own, so an open part joined to a closed body (a lathe's residual band)
      does not stop the body from burying (WI 2120's mug: 54 % of its source inside the lathe body);
    - rebuild to source: a rebuild that encloses its source buries every source point, so only this
      direction sees a box around a sphere.
    Returns (p95, the source-to-rebuild p95, the rebuild-to-source p95, the buried share)."""
    pts, _ = trimesh.sample.sample_surface(source_w, n, seed=7)
    w = welded(lod0)
    _, d, _ = trimesh.proximity.closest_point(w, pts)
    d = d / size
    inside = np.zeros(len(pts), bool)
    # split without repair: trimesh's default fills a piece's holes, which would close an open part
    for piece in w.split(only_watertight=False, repair=False):
        if piece.is_watertight:
            inside |= piece.contains(pts)
    buried = inside & (d > BURIED)
    # a rebuild enclosing all its source buries every point: then only the other direction speaks
    forward = float(np.percentile(d[~buried], 95)) if (~buried).any() else 0.0
    back_pts, _ = trimesh.sample.sample_surface(w, n // 4, seed=9)
    _, e, _ = trimesh.proximity.closest_point(source_w, back_pts)
    backward = float(np.percentile(e / size, 95))
    return max(forward, backward), forward, backward, float(buried.mean())


def colour_rows(renders):
    """Per even-light view, the rebuild's mean colour against the source's, as the largest channel's
    difference in percent. Pixels with alpha > 0 only."""
    rows = {}
    for key, path in renders.items():
        if not key.startswith("source_"):
            continue
        view = key[len("source_"):]
        means = []
        for p in (path, renders[f"rebuild_{view}"]):
            a = np.asarray(Image.open(p).convert("RGBA")).astype(float)
            mask = a[..., 3] > 0
            means.append(a[mask][:, :3].mean(axis=0) if mask.any() else np.zeros(3))
        rel = (means[1] - means[0]) / np.maximum(means[0], 1) * 100
        rows[view] = round(float(np.abs(rel).max()), 2)
    return rows


def hull_over_volume(lod0):
    w = welded(lod0)
    if not w.is_watertight or w.volume <= 0:
        return None
    return round(float(w.convex_hull.volume / w.volume), 3)
