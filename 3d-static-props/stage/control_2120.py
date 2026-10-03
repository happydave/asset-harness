#!/usr/bin/env python3
"""The control for the gate's new rows: pieces against the source's parts, floating parts, the two-way
shape and the colour, run with no rebuild over WI 2120's generic outputs on ai2.

control_2120.py RUN_DIR NAME...   (RUN_DIR: WI 2120's run folder, holding src/ and out/)

Prints one row a prop and the new rows' verdict. The colour row is WI 2120's own (its sheet.txt, the
worst of its views), since its renders are not this stage's.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure  # noqa: E402
import parts as P  # noqa: E402
from common import load_zup  # noqa: E402

run, names = sys.argv[1], sys.argv[2:]
print("| Prop | Source parts | Rebuild pieces | Floating | Shape p95 | Worst view | New rows |")
print("|---|---|---|---|---|---|---|")
for n in names:
    o = os.path.join(run, "out", n)
    norm = json.load(open(os.path.join(o, "norm.json")))
    src = load_zup(os.path.join(run, "src", f"{n}.glb"), norm["matrix"])
    size = float(max(src.extents))
    w, _, info = P.source_parts(src, size)
    lod0 = load_zup(os.path.join(o, "final", f"{n}_lod0.glb"))
    fl, pieces = measure.floating(lod0, size)
    p95, _, _, _ = measure.shape_p95(w, lod0, size)
    rows = [l for l in open(os.path.join(o, "sheet.txt")).read().splitlines() if "rebuilt" in l]
    worst = max(max(abs(float(v)) for v in re.search(r"\[([^\]]*)\] %", l).group(1).split()) for l in rows)
    ok = pieces <= info["parts"] and not fl and p95 <= 0.04 and worst <= 5.0
    print(f"| {n} | {info['parts']} | {pieces} | {len(fl)} | {p95 * 100:.1f} % | {worst:.1f} % | {'accept' if ok else 'refuse'} |",
          flush=True)
