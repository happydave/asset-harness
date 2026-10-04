"""The gate: every row with its value and limit; any failed row refuses the arm."""

SHAPE_P95 = 0.04   # the two-way p95 distance, as a share of the size
# the box arm's own: a fitted box cannot follow faces sculpted in relief. WI 2091's crate, a good box by
# eye, reads 5.73 % (its panels sit about 4 % inside its frame boards); WI 2120's domed chest reads 11.8 %
SHAPE_P95_BOX = 0.06
COLOUR = 5.0       # the bake's largest per-view mean-colour difference, percent
# the view from above (elevation 55) sees top faces and shelf interiors at a slant, and in play the camera
# stands near a prop's side: WI 2120's bookshelf and book stack held by eye at 7.4 % and 6.1 % from above
COLOUR_ABOVE = 8.0
SIZE_TOL = 0.05    # the governing axis within this share of the category's size
FOOT = 0.001       # yards


def row(ok, value, limit):
    return {"pass": bool(ok), "value": value, "limit": limit}


def rows(m):
    """m: the measurements of one arm's output, with the arm's name under "arm" when it has its own limits."""
    shape_limit = SHAPE_P95_BOX if m.get("arm") == "box" else SHAPE_P95
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
        "shape": row(m["shape_p95"] <= shape_limit, round(m["shape_p95"], 4), f"<= {shape_limit}"),
        "colour": row(all(v <= (COLOUR_ABOVE if k == "above" else COLOUR) for k, v in m["colour"].items()),
                      m["colour"], f"each view <= {COLOUR} %, above <= {COLOUR_ABOVE} %"),
    }
    r.update({k: row(ok, detail, "0 errors") for k, (ok, detail) in m["validator"].items()})
    return r


def passed(r):
    return all(v["pass"] for v in r.values())
