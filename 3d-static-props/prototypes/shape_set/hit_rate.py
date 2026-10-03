"""WI 2120's hit rate by shape class. hit_rate.py OUTDIR MANIFEST LOOK.json

A prop holds by the numbers when the rebuild is one closed piece, the source is within 4 % of the
size at p95 and the bake within 5 % in every view (the 2112 holders' worst: 3.3 % and 2.1 %). The
look (LOOK.json: name -> [hold|fail, note]) is the sheet read by eye; a hit needs both.
"""
import json
import re
import sys
from collections import defaultdict

out, manifest, look = sys.argv[1], json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))


def numbers(s):
    st = json.load(open(f"{out}/{s}/stats.json"))
    rows = [l for l in open(f"{out}/{s}/sheet.txt").read().splitlines() if "rebuilt" in l]
    worst = max(max(abs(float(v)) for v in re.search(r"\[([^\]]*)\] %", l).group(1).split()) for l in rows)
    p95 = st["source_to_rebuild_share_of_size"]["p95"] * 100
    try:
        p95 = json.load(open(f"{out}/{s}/outside.json"))["p95"] * 100
    except OSError:
        pass
    ok = st["rebuild_pieces"] == 1 and st["rebuild_watertight"] and p95 <= 4 and worst <= 5
    return ok, st["rebuild_pieces"], p95, worst, st["gate_pass"]


by_class = defaultdict(list)
print("| Prop | Class | Pieces | p95 | Worst view | Gate | Numbers | Look | Hit | Note |")
print("|---|---|---|---|---|---|---|---|---|---|")
for item in manifest["items"]:
    s, c = item["name"], item["class"]
    try:
        ok, pieces, p95, worst, gate = numbers(s)
    except OSError:
        by_class[c].append(None)
        print(f"| {s} | {c} | | | | | not run | | | |")
        continue
    seen, note = look.get(s, ["—", ""])
    hit = ok and seen == "hold"
    by_class[c].append((ok, seen == "hold", hit))
    print(f"| {s} | {c} | {pieces} | {p95:.1f} % | {worst:.1f} % | {'pass' if gate else 'fail'} "
          f"| {'hold' if ok else 'fail'} | {seen} | {'yes' if hit else 'no'} | {note} |")

print()
print("| Class | Props | Run | Hold by the numbers | Hold by look | Hits (both) |")
print("|---|---|---|---|---|---|")
total = [0, 0, 0, 0]
for c, rows in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
    run = [r for r in rows if r is not None]
    k = [sum(r[i] for r in run) for i in range(3)]
    total = [total[0] + len(run)] + [total[i + 1] + k[i] for i in range(3)]
    cell = (lambda n: f"{n}/{len(run)}") if run else (lambda n: "—")
    print(f"| {c} | {len(rows)} | {len(run)} | {cell(k[0])} | {cell(k[1])} | {cell(k[2])} |")
print(f"| all | {sum(len(r) for r in by_class.values())} | {total[0]} | {total[1]}/{total[0]} | {total[2]}/{total[0]} | {total[3]}/{total[0]} |")
