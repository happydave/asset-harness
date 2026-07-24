#!/usr/bin/env python3
"""WI 1037: compare the OWNER's blind ranking against the machine rankings -> the spike verdict.

Ground truth is the owner's ordering (their taste is what auto-promotion must match). For each group and
each scorer we report:
  * top-1 agreement -- does the scorer's best pick equal the owner's best pick? (what auto-promote needs)
  * Spearman rho    -- does the whole ordering agree? (+1 identical, 0 unrelated, -1 inverted)

A scorer that is merely *weak* (rho ~ 0) argues for cull-only; a scorer that is *anti*-correlated
(rho < 0) argues it must not drive selection at all.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent / "outputs" / "spike1037"

# Owner's blind ranking, best -> worst (from ranking/ranking_form.md, filled 2026-07-24).
OWNER = {
    "shot4": ["E", "B", "C", "A", "D"],
    "shot7": ["D", "C", "B", "A", "E"],
    # Songs were listed by seed, not lettered (a form bug); the owner answered positionally, so
    # A=seed701, B=seed702, C=seed703, D=seed704 in listed order. FLAGGED for confirmation.
    "songs": ["seed701", "seed704", "seed703", "seed702"],
}


def spearman(order_a, order_b):
    """rho between two orderings of the same items (lists, best-first)."""
    items = list(order_a)
    ra = {n: i + 1 for i, n in enumerate(order_a)}
    rb = {n: i + 1 for i, n in enumerate(order_b)}
    n = len(items)
    d2 = sum((ra[i] - rb[i]) ** 2 for i in items)
    return 1 - (6 * d2) / (n * (n * n - 1))


def order_from_ranks(rank_map):
    """{name: rank} -> [names best-first]"""
    return [k for k, _ in sorted(rank_map.items(), key=lambda kv: kv[1])]


def main():
    scores = json.loads((HERE / "machine_scores.json").read_text())
    key = json.loads((SPIKE / "ranking" / "_label_key.json").read_text())
    rows = []

    for group in ("shot4", "shot7"):
        owner_files = [key[group][letter] for letter in OWNER[group]]
        g = scores["images"][group]
        for scorer, rk in (("PickScore", "rank_pickscore"), ("CLIPScore", "rank_clip")):
            ranks = {k: v for k, v in g.get(rk, {}).items() if k in owner_files}
            if len(ranks) != len(owner_files):
                continue
            m_order = order_from_ranks(ranks)
            rows.append((group, scorer, owner_files[0], m_order[0],
                         owner_files[0] == m_order[0], spearman(owner_files, m_order)))

    a = scores.get("audio", {})
    if a.get("rank_clap"):
        m_order = order_from_ranks(a["rank_clap"])
        owner_order = OWNER["songs"]
        rows.append(("songs", "CLAP", owner_order[0], m_order[0],
                     owner_order[0] == m_order[0], spearman(owner_order, m_order)))

    print(f"{'group':7s} {'scorer':10s} {'owner top':28s} {'machine top':28s} {'top1':5s} {'rho':>6s}")
    for g, s, ot, mt, ok, rho in rows:
        print(f"{g:7s} {s:10s} {ot:28s} {mt:28s} {'MATCH' if ok else ' miss':5s} {rho:+6.2f}")

    top1 = sum(1 for r in rows if r[4])
    print(f"\ntop-1 agreement: {top1}/{len(rows)} scorer-group pairs")
    for s in ("PickScore", "CLIPScore", "CLAP"):
        rs = [r[5] for r in rows if r[1] == s]
        if rs:
            print(f"  mean rho {s:10s} = {sum(rs)/len(rs):+.2f}   (per-group: "
                  f"{', '.join(f'{x:+.2f}' for x in rs)})")


if __name__ == "__main__":
    main()
