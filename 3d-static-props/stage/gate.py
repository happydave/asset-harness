"""The gate: every row with its value and limit; any failed row refuses the arm."""

SHAPE_P95 = 0.04   # the source-to-rebuild p95, as a share of the size
COLOUR = 5.0       # the bake's largest per-view mean-colour difference, percent
SIZE_TOL = 0.05    # the governing axis within this share of the category's size
FOOT = 0.001       # yards


def row(ok, value, limit):
    return {"pass": bool(ok), "value": value, "limit": limit}


def rows(m):
    """m: the measurements of one arm's output."""
    r = {
        "triangles": row(m["lod0_tris"] <= m["budget"], m["lod0_tris"], f"<= {m['budget']}"),
        "lods_decrease": row(m["lod1_tris"] < m["lod0_tris"] and m["lod2_tris"] < m["lod1_tris"],
                             [m["lod0_tris"], m["lod1_tris"], m["lod2_tris"]], "each below the last"),
        "texture": row(m["texture"] <= m["texture_limit"], m["texture"], f"<= {m['texture_limit']}"),
        "foot_on_ground": row(abs(m["foot"]) <= FOOT, round(m["foot"], 5), f"|z| <= {FOOT}"),
        "size": row(abs(m["governing"] - m["size"]) <= SIZE_TOL * m["size"], round(m["governing"], 4),
                    f"{m['size']} +/- {SIZE_TOL:.0%} ({m['governing_axis']})"),
        "collision": row(m["collision_tris"] > 0 and m["collision_watertight"],
                         f"{m['collision_tris']} triangles, watertight {m['collision_watertight']}", "present, watertight"),
        "pieces": row(m["pieces"] <= m["source_parts"], m["pieces"], f"<= {m['source_parts']} (the source's parts)"),
        "floating": row(not m["floating"], m["floating"], "no piece apart from the others and the ground"),
        "shape": row(m["shape_p95"] <= SHAPE_P95, round(m["shape_p95"], 4), f"<= {SHAPE_P95}"),
        "colour": row(max(m["colour"].values()) <= COLOUR, m["colour"], f"each view <= {COLOUR} %"),
    }
    r.update({k: row(ok, detail, "0 errors") for k, (ok, detail) in m["validator"].items()})
    return r


def passed(r):
    return all(v["pass"] for v in r.values())
