"""A source's parts, the geometry of the arms built outside Blender (the lathe and the parts arm), and the
box arm's fitted box.

All in the normalised z-up frame, sizes as shares of the prop's size (its largest extent).
"""
import numpy as np
import trimesh

from common import welded
from simplify import simplify

CONTACT = 0.01      # parts closer than this share of the size are one part
AREA_FLOOR = 0.01   # a part under this share of the source's area is not counted
LATHE_TOL = 0.04    # source surface further than this outside the lathe is rebuilt as a residual part
PART_FLOOR = 12     # the fewest triangles a rebuilt part gets
MIN_SIDES = 12      # the lathe's fewest sides
OPEN_DEPTH = 0.25   # a top cap dipping this share of the height inside the rim is an open mouth
WALL = 0.02         # inner-wall points lie at least this share of the size inside the outer profile
FIT_P95 = 0.04      # a part's fit is taken when its p95 distance is within this share of the size


class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def source_parts(mesh, size, contact=CONTACT, area_floor=AREA_FLOOR):
    """The source's parts: welded components merged when within `contact` of each other (a grid of
    cells that size; components in the same or neighbouring cells merge), keeping each merged part with
    at least `area_floor` of the source's area. Returns the welded mesh, the parts as face-index arrays
    (largest first), and what was found."""
    w = welded(mesh)
    comps = trimesh.graph.connected_components(w.face_adjacency, nodes=np.arange(len(w.faces)), min_len=1)
    label = np.empty(len(w.faces), int)
    for i, c in enumerate(comps):
        label[c] = i
    d = contact * size
    # each component's occupied cells, from its vertices and from points sampled over its surface at
    # about the contact distance (a coarse face's corners alone can miss where two parts touch)
    n = int(min(2_000_000, max(1000, 2 * w.area / (d * d))))
    samples, face_of = trimesh.sample.sample_surface(w, n, seed=13)
    pts = np.vstack([w.vertices[w.faces].reshape(-1, 3), samples])
    lab = np.concatenate([np.repeat(label, 3), label[face_of]])
    cells = np.floor(pts / d).astype(np.int64)
    key = np.unique(np.column_stack([cells, lab]), axis=0)
    by_cell = {}
    for x, y, z, c in key:
        by_cell.setdefault((x, y, z), set()).add(int(c))
    u = _Union(len(comps))
    offsets = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)]
    for (x, y, z), cs in by_cell.items():
        cs = list(cs)
        for c in cs[1:]:
            u.join(cs[0], c)
        for dx, dy, dz in offsets:
            other = by_cell.get((x + dx, y + dy, z + dz))
            if other:
                for c in other:
                    u.join(cs[0], c)
    roots = np.array([u.find(i) for i in range(len(comps))])
    root = roots[label]
    area = w.area_faces
    total = area.sum()
    parts, dropped = [], 0
    for r in np.unique(root):
        faces = np.nonzero(root == r)[0]
        if area[faces].sum() >= area_floor * total:
            parts.append(faces)
        else:
            dropped += 1
    parts.sort(key=lambda f: -area[f].sum())
    info = {"fragments": len(comps), "merged": int(len(np.unique(root))), "parts": len(parts),
            "dropped_small": dropped, "contact": contact, "area_floor": area_floor}
    return w, parts, info


def submesh(w, faces):
    m = trimesh.Trimesh(w.vertices, w.faces[faces], process=False)
    m.remove_unreferenced_vertices()
    return m


def p95_to(surface_of, target, size, n=4000):
    """The p95 distance from points on `surface_of` to `target`'s surface, as a share of the size."""
    pts, _ = trimesh.sample.sample_surface(surface_of, n, seed=11)
    _, dist, _ = trimesh.proximity.closest_point(target, pts)
    return float(np.percentile(dist, 95) / size)


def fit_error(part, fitted, size, n=4000):
    """A fit's error both ways: a fitted shape larger than its part is as wrong as one that misses it."""
    return max(p95_to(part, fitted, size, n), p95_to(fitted, part, size, n // 2))


def obb_box(mesh):
    """The oriented bounding box as a closed 12-triangle mesh."""
    tf, ext = trimesh.bounds.oriented_bounds(mesh)
    return trimesh.creation.box(extents=np.maximum(ext, 1e-4), transform=np.linalg.inv(tf))


# ---- the lathe -------------------------------------------------------------------------------------

def _frame(axis):
    """Rows: the axis, then two perpendiculars."""
    a = np.eye(3)[axis]
    b = np.eye(3)[(axis + 1) % 3]
    c = np.eye(3)[(axis + 2) % 3]
    return np.vstack([a, b, c])


def _outer_profile(pts, centre, frame, slices=48, sectors=24):
    """Per slice along the axis: the sectors' largest radius about the axis line, and their spread."""
    local = (pts - centre) @ frame.T
    t, p = local[:, 0], local[:, 1:]
    r = np.hypot(p[:, 0], p[:, 1])
    ang = np.arctan2(p[:, 1], p[:, 0])
    edges = np.linspace(t.min(), t.max(), slices + 1)
    prof, cvs = [], []
    for k in range(slices):
        sel = (t >= edges[k]) & (t <= edges[k + 1])
        if sel.sum() < 30:
            prof.append(np.nan)
            continue
        sec = np.floor((ang[sel] + np.pi) / (2 * np.pi) * sectors).astype(int) % sectors
        mx = np.full(sectors, np.nan)
        for s in range(sectors):
            rs = r[sel][sec == s]
            if len(rs):
                mx[s] = rs.max()
        good = mx[~np.isnan(mx)]
        if len(good) < sectors * 0.75:
            prof.append(np.nan)
            continue
        prof.append(float(np.median(good)))
        cvs.append(float(good.std() / max(good.mean(), 1e-9)))
    return edges, np.array(prof), (float(np.mean(cvs)) if cvs else np.inf)


def _circle(xy):
    """The least-squares circle through 2-D points: its centre and radius."""
    a = np.column_stack([2 * xy, np.ones(len(xy))])
    b = (xy ** 2).sum(axis=1)
    sol = np.linalg.lstsq(a, b, rcond=None)[0]
    return sol[:2], float(np.sqrt(max(sol[2] + sol[:2] @ sol[:2], 0.0)))


def _axis_centre(pts, centre, frame, slices=48, sectors=24, rounds=3):
    """The axis line through the body's cross-sections, not its bounding box: a handle or a cradle shifts the
    box's centre off the body's axis. Per slice, a circle is fitted to the sectors' outermost points and
    refitted without the points far off it (the attachment); the slices' median centre moves the axis."""
    c = np.asarray(centre, float).copy()
    for _ in range(rounds):
        local = (pts - c) @ frame.T
        t, p = local[:, 0], local[:, 1:]
        ang = np.arctan2(p[:, 1], p[:, 0])
        r = np.hypot(p[:, 0], p[:, 1])
        edges = np.linspace(t.min(), t.max(), slices + 1)
        shifts = []
        for k in range(slices):
            sel = np.nonzero((t >= edges[k]) & (t <= edges[k + 1]))[0]
            if len(sel) < 60:
                continue
            sec = np.floor((ang[sel] + np.pi) / (2 * np.pi) * sectors).astype(int) % sectors
            rim = np.array([p[sel[sec == s][np.argmax(r[sel[sec == s]])]] for s in range(sectors) if (sec == s).any()])
            if len(rim) < sectors * 0.75:
                continue
            cen, rad = _circle(rim)
            off = np.abs(np.hypot(*(rim - cen).T) - rad)
            keep = off <= max(2 * np.median(off), 1e-9)
            if keep.sum() >= 8:
                cen, rad = _circle(rim[keep])
            shifts.append(cen)
        if not shifts:
            break
        move = np.median(np.array(shifts), axis=0)
        c = c + move @ frame[1:]
        if np.linalg.norm(move) < 1e-6:
            break
    return c


def _caps(pts, centre, frame, rmax, bins=16):
    """The top and bottom surfaces by radius: per radial bin, the highest and lowest point along the axis.
    Returns (r, top_t, bottom_t) for the bins with points."""
    local = (pts - centre) @ frame.T
    t, r = local[:, 0], np.hypot(local[:, 1], local[:, 2])
    edges = np.linspace(0, rmax, bins + 1)
    out = []
    for k in range(bins):
        sel = (r >= edges[k]) & (r < edges[k + 1])
        if sel.sum() >= 5:
            out.append(((edges[k] + edges[k + 1]) / 2, float(t[sel].max()), float(t[sel].min())))
    return np.array(out)


def _inner_wall(pts, centre, frame, edges, outer, wall, sectors=24):
    """Per slice along the axis: the inner wall's radius, from the points lying more than `wall` inside the
    outer profile (the sectors' largest such radius, their median), or NaN where too few sectors have one."""
    local = (pts - centre) @ frame.T
    t, r = local[:, 0], np.hypot(local[:, 1], local[:, 2])
    ang = np.arctan2(local[:, 2], local[:, 1])
    out = []
    for k in range(len(edges) - 1):
        sel = (t >= edges[k]) & (t <= edges[k + 1])
        if np.isnan(outer[k]):
            out.append(np.nan)
            continue
        sel &= r < outer[k] - wall
        if sel.sum() < 30:
            out.append(np.nan)
            continue
        sec = np.floor((ang[sel] + np.pi) / (2 * np.pi) * sectors).astype(int) % sectors
        mx = [r[sel][sec == s].max() for s in range(sectors) if (sec == s).any()]
        out.append(float(np.median(mx)) if len(mx) >= sectors // 2 else np.nan)
    return np.array(out)


def _rdp(points, tol):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    n = np.linalg.norm(ab)
    if n == 0:
        d = np.linalg.norm(points - a, axis=1)
    else:
        p = points - a
        d = np.abs(ab[0] * p[:, 1] - ab[1] * p[:, 0]) / n
    i = int(np.argmax(d))
    if d[i] > tol:
        return np.vstack([_rdp(points[: i + 1], tol)[:-1], _rdp(points[i:], tol)])
    return np.vstack([a, b])


def _revolve(profile, sides, frame, centre):
    """A closed surface of revolution from (t, r) points running from the axis, round the outside, back
    to the axis: each end on the axis is one pole vertex."""
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    verts, faces, rows = [], [], []
    for t, r in profile:
        if r <= 1e-9:
            rows.append([len(verts)])
            verts.append([t, 0.0, 0.0])
        else:
            rows.append(list(range(len(verts), len(verts) + sides)))
            verts += [[t, r * np.cos(a), r * np.sin(a)] for a in ang]
    for ra, rb in zip(rows, rows[1:]):
        if len(ra) == 1 and len(rb) == 1:
            continue  # two points on the axis in a row bound no surface
        for j in range(sides):
            if len(ra) == 1:
                faces.append([ra[0], rb[(j + 1) % sides], rb[j]])
            elif len(rb) == 1:
                faces.append([ra[j], ra[(j + 1) % sides], rb[0]])
            else:
                a0, a1, b0, b1 = ra[j], ra[(j + 1) % sides], rb[j], rb[(j + 1) % sides]
                faces += [[a0, a1, b0], [a1, b1, b0]]
    if not faces:
        return None  # every point on the axis: no surface
    v = np.asarray(verts) @ frame + centre
    m = trimesh.Trimesh(v, np.asarray(faces), process=True)
    trimesh.repair.fix_normals(m)
    return m


def _tris(profile, sides):
    rows = [1 if r <= 1e-9 else sides for _, r in profile]
    return sum(sides if 1 in (a, b) else 2 * sides for a, b in zip(rows, rows[1:]))


def lathe(mesh, size, budget):
    """The lathe arm's geometry, or None with the reason. Returns (mesh, info, shape), shape being the
    frame, centre and (t, r) profile the residual test reads."""
    pts, _ = trimesh.sample.sample_surface(mesh, 30000, seed=5)
    lo, hi = mesh.bounds
    box_centre = (lo + hi) / 2
    best = None
    for axis in range(3):
        frame = _frame(axis)
        centre = _axis_centre(pts, box_centre, frame)
        edges, prof, cv = _outer_profile(pts, centre, frame)
        if best is None or cv < best[0]:
            best = (cv, axis, frame, edges, prof, centre)
    cv, axis, frame, edges, prof, centre = best
    info = {"axis": "xyz"[axis], "circularity_cv": round(cv, 4),
            "axis_shift": round(float(np.linalg.norm((centre - box_centre) @ frame[1:].T)) / size, 4)}
    if not np.isfinite(cv) or cv > 0.15:
        return None, {**info, "why": "no axis has circular cross-sections (cv over 0.15)"}, None
    mids = (edges[:-1] + edges[1:]) / 2
    ok = ~np.isnan(prof)
    side = np.column_stack([mids[ok], prof[ok]])
    # closed: the bottom surface out from the axis, up the side, the top surface back in to the axis
    caps = _caps(pts, centre, frame, float(side[:, 1].max()))
    inner = caps[caps[:, 0] < side[0, 1]] if len(caps) else caps
    bottom = [(edges[0], 0.0)] + [(b, r) for r, _, b in inner] + [(edges[0], side[0, 1])]
    inner = caps[caps[:, 0] < side[-1, 1]] if len(caps) else caps
    # an open vessel: from above, the highest point near the axis is the inside floor, seen through the
    # mouth. A cap through it cuts a cone across the hollow (WI 2120's jar: 22 % at p95), so the profile
    # follows the inner wall from the rim down to the floor instead.
    height = edges[-1] - edges[0]
    deep = inner[:, 1] < edges[-1] - OPEN_DEPTH * height if len(inner) else np.zeros(0, bool)
    mouth = int(np.argmin(deep)) if len(deep) and not deep.all() else len(deep)
    if mouth > 0:
        floor_t = float(np.median(inner[:mouth, 1]))
        wall = _inner_wall(pts, centre, frame, edges, prof, WALL * size)
        mids = (edges[:-1] + edges[1:]) / 2
        down = [(m, w) for m, w in zip(mids[::-1], wall[::-1]) if not np.isnan(w) and m > floor_t]
        rim = inner[mouth:]
        top = [(edges[-1], side[-1, 1])] + [(tp, r) for r, tp, _ in rim[::-1]] + down
        top += [(floor_t, down[-1][1] if down else float(inner[mouth - 1, 0])), (floor_t, 0.0)]
        info["open_top"] = {"floor_t": round(floor_t / size, 4), "wall_slices": len(down)}
    else:
        top = [(edges[-1], side[-1, 1])] + [(tp, r) for r, tp, _ in inner[::-1]] + [(edges[-1], 0.0)]
    pts2 = np.array(bottom + [tuple(p) for p in side] + top, float)
    # each side count with the finest profile that fits the budget; the closest fit to the source wins
    fits = []
    for sides in (16, 14, MIN_SIDES):
        tol = 0.004 * size
        while True:
            simple = _rdp(pts2, tol)
            simple[0, 1] = simple[-1, 1] = 0.0
            tris = _tris(simple, sides)
            if tris <= budget or tol > 0.1 * size:
                break
            tol *= 1.4
        body = _revolve(simple, sides, frame, centre) if tris <= budget else None
        if body is not None:
            fits.append((fit_error(mesh, body, size, n=3000), sides, simple, body, tol))
    if not fits:
        return None, {**info, "why": f"no profile fits {budget} triangles with {MIN_SIDES} sides"}, None
    err, sides, simple, body, tol = min(fits, key=lambda f: f[0])
    info.update({"sides": sides, "profile_points": int(len(simple)), "triangles": int(len(body.faces)),
                 "fit_p95": round(err, 4), "candidates": [[f[1], round(f[0], 4)] for f in fits]})
    return body, info, {"frame": frame, "centre": centre, "profile": simple, "tolerance": tol}


def residual_faces(w, shape, size, tol=LATHE_TOL, reach=0.005):
    """Source faces lying outside the lathe, as connected clusters: a cluster of faces beyond the
    profile by more than `reach` of the size, kept when part of it stands out by more than `tol`. The
    cluster reaches down to the body, so its rebuilt part touches the lathe instead of floating off it."""
    local = (w.triangles_center - shape["centre"]) @ shape["frame"].T
    t, r = local[:, 0], np.hypot(local[:, 1], local[:, 2])
    prof = shape["profile"]
    # the profile's outer envelope: the largest radius at each height, from points along its segments
    seg = np.vstack([np.linspace(prof[i], prof[i + 1], 32) for i in range(len(prof) - 1)])
    bins = np.linspace(seg[:, 0].min(), seg[:, 0].max(), 65)
    which = np.clip(np.digitize(seg[:, 0], bins) - 1, 0, 63)
    env = np.array([seg[which == k, 1].max() if (which == k).any() else 0.0 for k in range(64)])
    mids = (bins[:-1] + bins[1:]) / 2
    rad = np.interp(t, mids, env)
    beyond = np.maximum(r - rad, np.maximum(bins[0] - t, t - bins[-1]))
    outside = np.nonzero(beyond > reach * size)[0]
    if len(outside) == 0:
        return []
    sub_adj = w.face_adjacency
    mask = np.zeros(len(w.faces), bool)
    mask[outside] = True
    keep = mask[sub_adj[:, 0]] & mask[sub_adj[:, 1]]
    groups = trimesh.graph.connected_components(sub_adj[keep], nodes=outside, min_len=1)
    # a cluster counts where part of it stands out past the tolerance plus the profile's own, since the
    # simplified profile may lie inside the surface by that much
    return [np.asarray(g) for g in groups if beyond[np.asarray(g)].max() > tol * size + shape.get("tolerance", 0.0)]


# ---- the parts arm ---------------------------------------------------------------------------------

def fit_part(part, size, share, allow_lathe=True):
    """A part rebuilt by the first fit within FIT_P95: a box, a lathe, or its own simplification."""
    box = obb_box(part)
    if len(box.faces) <= share and fit_error(part, box, size) <= FIT_P95:
        return box, "box"
    if allow_lathe and share >= 2 * MIN_SIDES * 2:
        body, _, _ = lathe(part, size, share)
        if body is not None and fit_error(part, body, size) <= FIT_P95:
            return body, "lathe"
    faces, how, _ = simplify(part.vertices, part.faces, max(PART_FLOOR, share), max_error=1.0)
    m = trimesh.Trimesh(part.vertices, faces, process=False)
    m.remove_unreferenced_vertices()
    return m, f"simplified ({how})"


def allocate(areas, budget, floor=PART_FLOOR):
    """Triangles per part: each kept part gets `floor`, and the rest of the budget is shared by area. The
    smallest parts are dropped until the floors fit. Returns the shares (0 for a dropped part)."""
    areas = np.asarray(areas, float)
    alive = np.ones(len(areas), bool)
    while alive.sum() * floor > budget and alive.any():
        idx = np.nonzero(alive)[0]
        alive[idx[int(np.argmin(areas[idx]))]] = False
    out = np.zeros(len(areas), int)
    if not alive.any():
        return out
    a = areas[alive]
    rest = budget - floor * int(alive.sum())
    out[alive] = floor + np.floor(rest * a / a.sum()).astype(int)
    return out


def parts_arm(w, parts, size, budget):
    """Each source part rebuilt on its own. Returns (mesh, info)."""
    meshes = [submesh(w, f) for f in parts]
    shares = allocate([m.area for m in meshes], budget)
    out, rows = [], []
    for i, (m, share) in enumerate(zip(meshes, shares)):
        if share == 0:
            rows.append({"part": i, "dropped": True, "area": round(float(m.area), 5)})
            continue
        built, how = fit_part(m, size, int(share))
        out.append(built)
        rows.append({"part": i, "share": int(share), "fit": how, "triangles": int(len(built.faces))})
    if not out:
        return None, {"why": "no part fits the budget", "parts": rows}
    return trimesh.util.concatenate(out), {"parts": rows}


def lathe_arm(w, parts, size, budget):
    """The lathe body, plus residual source parts outside it rebuilt by the parts arm."""
    body, info, shape = lathe(w, size, budget)
    if body is None:
        return None, info
    area = w.area_faces
    groups = [g for g in residual_faces(w, shape, size) if area[g].sum() >= 0.005 * area.sum()]
    info["residual_parts"] = len(groups)
    if not groups:
        return body, info
    # residual parts need room: the body again with a reserve kept for them
    reserve = min(budget // 3, 4 * PART_FLOOR)
    body, info, shape = lathe(w, size, budget - reserve)
    if body is None:
        return None, info
    info["residual_parts"] = len(groups)
    room = budget - len(body.faces)
    res, rinfo = parts_arm(w, groups, size, room)
    info["residual"] = rinfo
    if res is None:
        return body, info
    return trimesh.util.concatenate([body, res]), info


# ---- the box arm's box ----------------------------------------------------------------------------

BOX_TRIMS = (0, 0.5, 1, 2, 3, 4, 5)   # percent of the surface samples each face may move in past
BOX_KEEP = 0.025                      # a trim may shorten the governing axis by this share at most


def box_bounds(w, size, governing):
    """The box arm's axis-aligned box, fitted to the body: each face but the bottom moved in past a share
    of the source's surface samples (BOX_TRIMS), the trim whose box fits the source best both ways taken,
    among those keeping the governing axis within BOX_KEEP of the source's (the best fit alone took 5 % off
    WI 2091's crate and failed its size row). A box on the extremes stands off the body by whatever sticks
    out (latches, caps, a cornice). Returns (low corner, high corner, info)."""
    pts, _ = trimesh.sample.sample_surface(w, 40000, seed=3)
    floor = float(w.bounds[0][2])

    def extent(lo, hi):
        return max(hi[0] - lo[0], hi[1] - lo[1]) if governing == "horizontal" else hi[2] - lo[2]

    full = extent(*w.bounds)
    best = None
    for s in BOX_TRIMS:
        lo = np.percentile(pts, s, axis=0)
        hi = np.percentile(pts, 100 - s, axis=0)
        lo[2] = floor
        if s and extent(lo, hi) < (1 - BOX_KEEP) * full:
            continue
        box = trimesh.creation.box(extents=np.maximum(hi - lo, 1e-4),
                                   transform=trimesh.transformations.translation_matrix((lo + hi) / 2))
        e = fit_error(w, box, size, n=3000)
        if best is None or e < best[0]:
            best = (e, s, lo, hi)
    e, s, lo, hi = best
    return lo, hi, {"trim_percent": s, "fit_p95": round(e, 4)}


def collision_boxes(w, parts):
    """One oriented box per source part, as one mesh of disjoint closed boxes."""
    return trimesh.util.concatenate([obb_box(submesh(w, f)) for f in parts])
