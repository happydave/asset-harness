#!/usr/bin/env python3
"""WI 1179: turn the judge's raw output into the verdict table, for any of the three protocols.

Reports agreement with the owner alongside the comparators the result has to beat — the WI 1045
scorers run on the SAME images, the trivial "always answer first" strategy, and the permutation null
(at n=5, rho >= +0.30 arises by chance 34% of the time, which is worth knowing before treating +0.30
as a bar) — plus each protocol's own position control.

    python3 vlm_report.py vlm_a_*.json vlm_b_*.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vlm_judge import permutation_p, spearman

HERE = Path(__file__).resolve().parent
B_PICKS = {"hero": 202, "lab": 101, "ranch": 303, "ai": 101, "readiness": 101, "games": 101}


def first_ranking(g):
    return g["runs"][0]["ranking"]


def group_controls(g, mode) -> str:
    runs = g["runs"]
    fwd = [r["ranking"] for r in runs if r["kind"] in ("forward", "pairwise")]
    det = "n/a" if len(fwd) < 2 else str(all(x == fwd[0] for x in fwd))
    if mode == "listwise":
        rev = next((r for r in runs if r["kind"] == "reversed"), None)
        pos = "n/a" if not rev else str(rev["ranking"] == fwd[0])
        return f"determinism {det:5} position-stable {pos}"
    if mode == "pairwise":
        r = runs[0]
        return f"determinism {det:5} order-flips {r['order_flips']}/{r['pairs']} ({r['flip_rate']:.0%})"
    ties = runs[0].get("ties", 0)
    scores = [s["score"] for s in runs[0]["scores"]]
    return f"determinism {det:5} tied-scores {ties}/{len(scores)}  scores {scores}"


def short(name: str) -> str:
    return name.replace(".png", "").split("_")[-1]


def report_a(d: dict) -> None:
    mode = d.get("mode", "listwise")
    print(f"\n=== CORPUS A · {Path(d['server']).name} · {mode} "
          f"(WI 1037, owner full ranking, n=5) ===")
    rhos = []
    for g in d["groups"]:
        ranking = first_ranking(g)
        if not ranking:
            print(f"{g['group']}: UNPARSEABLE")
            continue
        sanity = [x for x in ranking if x.startswith("sanity")]
        judged = [x for x in ranking if not x.startswith("sanity")]
        owner = g["owner_order"]
        rho = spearman(owner, judged)
        rhos.append(rho)
        print(f"\n{g['group']}:  owner {[short(n) for n in owner]}")
        print(f"          judge {[short(n) for n in judged]}")
        print(f"          rho {rho:+.2f} (p={permutation_p(rho, len(owner)):.3f})  "
              f"top-1 {'MATCH' if judged[0] == owner[0] else 'miss'}")
        print(f"          {group_controls(g, mode)}")
        if sanity:
            pos = ranking.index(sanity[0]) + 1
            print(f"          sanity floor: off-brief placed {pos}/{len(ranking)} "
                  f"{'PASS' if pos == len(ranking) else 'FAIL'}")
    if rhos:
        print(f"\nmean rho {sum(rhos)/len(rhos):+.3f}   "
              f"baseline PickScore-letterbox +0.30   p(rho>=+0.30 by chance) = {permutation_p(0.30, 5):.2f}")


def report_b(d: dict) -> None:
    mode = d.get("mode", "listwise")
    base = json.loads((HERE / "baseline_corpus_b.json").read_text())
    print(f"\n=== CORPUS B · {mode} (WI 1111 imagery, owner pick only, n=3) ===")
    hits = 0
    for g in d["groups"]:
        ranking = first_ranking(g)
        if not ranking:
            print(f"{g['group']}: UNPARSEABLE")
            continue
        hit = ranking[0] == g["owner_pick"]
        hits += hit
        print(f"{g['group']:10} owner {short(g['owner_pick']):5} judge {short(ranking[0]):5} "
              f"{'HIT ' if hit else 'miss'}  {group_controls(g, mode)}")
    n = len(d["groups"])
    bl = {k: sum(base[s][f"order_{k}"][0] == f"{s}_s{B_PICKS[s]}.png" for s in B_PICKS)
          for k in ("clip_letterbox", "pickscore_letterbox")}
    print(f"\nVLM top-1 {hits}/{n}   PickScore {bl['pickscore_letterbox']}/{n}   "
          f"CLIP {bl['clip_letterbox']}/{n}   'always first-listed seed' 4/{n}   random {n/3:.0f}/{n}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()
    for f in args.files:
        d = json.loads(f.read_text())
        (report_a if d["corpus"] == "a" else report_b)(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
