"""One Markdown row per prop from a chain run's outputs. table.py OUTDIR NAME..."""
import json
import re
import sys

out, names = sys.argv[1], sys.argv[2:]
print("| Prop | Stable pose's tilt | Size (yd, x × y × z) | Faces; LOD1, LOD2 | Bake: worst view; black | Source to rebuild: p95; max | Pieces | Hull tris; over volume | Gate |")
print("|---|---|---|---|---|---|---|---|---|")
for s in names:
    try:
        n = json.load(open(f"{out}/{s}/norm.json"))
        st = json.load(open(f"{out}/{s}/stats.json"))
        black = re.search(r"black texels inside ([0-9.]+)", open(f"{out}/{s}/empty.txt").read()).group(1)
        rows = [l for l in open(f"{out}/{s}/sheet.txt").read().splitlines() if "rebuilt" in l]
        worst = max(max(abs(float(v)) for v in re.search(r"\[([^\]]*)\] %", l).group(1).split()) for l in rows)
    except (OSError, AttributeError, ValueError) as e:
        print(f"| {s} | no result ({type(e).__name__}) | | | | | | | |")
        continue
    d = st["source_to_rebuild_share_of_size"]
    size = " × ".join(f"{v:.2f}" for v in n["extents_after"])
    closed = "closed" if st["rebuild_watertight"] else "open"
    hv = st["hull_volume_over_rebuild"]
    print(f"| {s} | {n['stable_pose_tilt_deg']:.0f}° | {size} | {st['rebuild_faces']}; {st['lods'][0]}, {st['lods'][1]} "
          f"| {worst:.1f} %; {float(black):.1f} % | {d['p95'] * 100:.1f} %; {d['max'] * 100:.1f} % "
          f"| {st['rebuild_pieces']}, {closed} | {st['hull_tris']}; {hv if hv is not None else '—'} "
          f"| {'pass' if st['gate_pass'] else 'fail'} |")
