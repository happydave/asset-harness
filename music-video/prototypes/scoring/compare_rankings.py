#!/usr/bin/env python3
"""WI 1045: compare the OWNER's blind ranking against machine rankings -- OLD harness vs CORRECTED.

Ground truth is the owner's ordering (their taste is what promotion must match). Per group and scorer:
  * top-1 agreement -- does the scorer's best pick equal the owner's best pick? (what auto-promote needs)
  * Spearman rho    -- does the whole ordering agree? (+1 identical, 0 unrelated, -1 inverted)

Reading both harnesses side by side is the point: WI 1037's numbers were produced by a harness that
showed the image scorers the middle square of a 16:9 frame and showed CLAP a RANDOM 10 s crop of a 75 s
song. Whether the correction moves the numbers is the question this answers -- "it changed nothing" is
as informative as "it changed everything", and asserting either without measuring is what got us here.

  v1 = scoring/machine_scores.json     (WI 1037, retained evidence)
  v2 = scoring/machine_scores_v2.json  (WI 1045, corrected)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent / "outputs" / "spike1037"

# Owner's blind ranking, best -> worst (from ranking/ranking_form.md, filled 2026-07-24).
OWNER = {
    "shot4": ["E", "B", "C", "A", "D"],
    "shot7": ["D", "C", "B", "A", "E"],
    # FLAGGED, unresolved: round 1 listed the songs by SEED while the image groups were lettered, so the
    # owner's "A,D,C,B" was read positionally (A=seed701 ... D=seed704). The form has since been fixed to
    # letter the songs, but THIS ordering still rests on that inference and is the weakest link below.
    "songs": ["seed701", "seed704", "seed703", "seed702"],
}
IMAGE_VARIANTS = [
    ("v1", "CLIPScore", "rank_clip"),
    ("v1", "PickScore", "rank_pickscore"),
    ("v2", "CLIPScore", "rank_clip_centrecrop"),
    ("v2", "CLIPScore", "rank_clip_letterbox"),
    ("v2", "CLIPScore", "rank_clip_multicrop"),
    ("v2", "PickScore", "rank_pickscore_centrecrop"),
    ("v2", "PickScore", "rank_pickscore_letterbox"),
    ("v2", "PickScore", "rank_pickscore_multicrop"),
]
AUDIO_VARIANTS = [
    ("v1", "CLAP", "rank_clap"),
    ("v2", "CLAP", "rank_clap"),
    ("v2", "Audiobox-CE", "rank_audiobox_CE"),
    ("v2", "Audiobox-PQ", "rank_audiobox_PQ"),
    ("v2", "Audiobox-CU", "rank_audiobox_CU"),
    ("v2", "Audiobox-PC", "rank_audiobox_PC"),
]


def spearman(order_a, order_b):
    """rho between two orderings of the same items (lists, best-first)."""
    ra = {n: i + 1 for i, n in enumerate(order_a)}
    rb = {n: i + 1 for i, n in enumerate(order_b)}
    n = len(order_a)
    d2 = sum((ra[i] - rb[i]) ** 2 for i in order_a)
    return 1 - (6 * d2) / (n * (n * n - 1))


def order_from_ranks(rank_map):
    return [k for k, _ in sorted(rank_map.items(), key=lambda kv: kv[1])]


def main():
    scores = {"v1": json.loads((HERE / "machine_scores.json").read_text()),
              "v2": json.loads((HERE / "machine_scores_v2.json").read_text())}
    key = json.loads((SPIKE / "ranking" / "_label_key.json").read_text())
    rows = []

    for group in ("shot4", "shot7"):
        owner_files = [key[group][letter] for letter in OWNER[group]]
        for ver, label, rk in IMAGE_VARIANTS:
            g = scores[ver]["images"].get(group, {})
            # filter to the ranked candidates (v2 also ranks the sanity control inside shot4);
            # relative order is preserved under filtering
            ranks = {k: v for k, v in g.get(rk, {}).items() if k in owner_files}
            if len(ranks) != len(owner_files):
                continue
            m = order_from_ranks(ranks)
            variant = rk.split("_")[-1] if ver == "v2" else "centrecrop"
            rows.append((group, ver, label, variant, owner_files[0], m[0],
                         owner_files[0] == m[0], spearman(owner_files, m)))

    owner_songs = OWNER["songs"]
    for ver, label, rk in AUDIO_VARIANTS:
        a = scores[ver].get("audio", {})
        ranks = {k: v for k, v in a.get(rk, {}).items() if k in owner_songs}
        if len(ranks) != len(owner_songs):
            continue
        m = order_from_ranks(ranks)
        variant = "whole-song" if ver == "v2" else "random 10s"
        rows.append(("songs", ver, label, variant, owner_songs[0], m[0],
                     owner_songs[0] == m[0], spearman(owner_songs, m)))

    print(f"{'group':6s} {'v':3s} {'scorer':12s} {'frame/window':12s} "
          f"{'owner top':22s} {'machine top':22s} {'top1':5s} {'rho':>6s}")
    for g, ver, s, variant, ot, mt, ok, rho in rows:
        print(f"{g:6s} {ver:3s} {s:12s} {variant:12s} {ot:22s} {mt:22s} "
              f"{'MATCH' if ok else ' miss':5s} {rho:+6.2f}")

    print("\nmean rho by scorer x treatment (images: over shot4+shot7):")
    seen = []
    for _, ver, s, variant, *_ in rows:
        if (ver, s, variant) not in seen:
            seen.append((ver, s, variant))
    for ver, s, variant in seen:
        rs = [r[7] for r in rows if (r[1], r[2], r[3]) == (ver, s, variant)]
        t1 = sum(1 for r in rows if (r[1], r[2], r[3]) == (ver, s, variant) and r[6])
        print(f"  {ver} {s:12s} {variant:12s} mean rho {sum(rs)/len(rs):+.2f}   "
              f"top-1 {t1}/{len(rs)}   (per-group: {', '.join(f'{x:+.2f}' for x in rs)})")

    tot = sum(1 for r in rows if r[6])
    print(f"\ntop-1 agreement overall: {tot}/{len(rows)} scorer-group pairs")


if __name__ == "__main__":
    main()
