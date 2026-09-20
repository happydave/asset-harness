#!/usr/bin/env python3
"""Re-run the matte stage and token export over an existing run root. Repair, not generation.

WI 1636: the mattes and tokens a previous run produced are alpha-inverted, and the fix is one node
in `chain.matte`. Regenerating the cast to deliver it would be wrong twice over -- it costs thirty
GPU jobs instead of four, and it would produce *different* masters, which the provenance rule
exists to prevent and `provenance.may_write` would refuse anyway.

So this reads each character's existing `style` derivative -- the matte stage's real input -- and
redoes only the tail:

    style.png -> matte -> tokens

    python3 reexport_mattes.py --root ~/wi1611/out_final --roster ../../roster/cast.csv \\
                               --input-dir ~/wi1626/input --server http://127.0.0.1:7126

Masters are never opened for writing. The master digests are recorded before and after and
compared, because an invariant that is only argued is an invariant that is only hoped for.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

import chain
import comfy_client as cc
import provenance as P
import roster as R
import tokens as T


def master_digests(root: Path, ids) -> dict[str, str]:
    out = {}
    for cid in ids:
        p = P.master_path(root, cid)
        if p.exists():
            out[cid] = chain.digest(p.read_bytes())
    return out


def reexport(ch, *, server, root: Path, input_dir: Path, scratch: Path) -> dict:
    style = P.derivative_path(root, ch.id, "style")
    if not style.exists():
        return {"id": ch.id, "skipped": f"no style derivative at {style}"}

    staged = input_dir / f"reexport_{ch.id}_style.png"
    staged.write_bytes(style.read_bytes())

    work = scratch / ch.id
    work.mkdir(parents=True, exist_ok=True)
    pid = cc.queue(server, chain.matte(staged.name, f"wi1636/{ch.id}_matte"))
    hist = cc.wait_for_history(server, pid, label=f"{ch.id}:matte")
    got = cc.download_outputs(server, hist, work / "matte", kinds=("images",))
    if not got:
        raise SystemExit(f"{ch.id}: matte stage produced no image")

    data = Path(got[0]).read_bytes()
    if not chain.figure_is_opaque(data):
        # The whole point of the exercise. Refusing here rather than writing means a re-export that
        # went the wrong way cannot quietly replace inverted artifacts with inverted artifacts.
        raise SystemExit(f"{ch.id}: re-exported matte is still not a cut-out -- "
                         f"{chain.explain_alpha(data)}")

    dest = P.derivative_path(root, ch.id, "matte")
    P.write_guarded(dest, "matte", data)

    written = {}
    if ch.targets:
        with Image.open(dest) as im:
            written = T.export(im, root, ch.id, ch.targets)
    return {"id": ch.id, "matte": str(dest), "polarity": "figure-opaque",
            "tokens": {k: str(v) for k, v in written.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="an existing run root, with masters/ and derivatives/")
    ap.add_argument("--roster", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:7126")
    ap.add_argument("--scratch", default="/tmp/wi1636")
    a = ap.parse_args()

    root, input_dir, scratch = Path(a.root), Path(a.input_dir), Path(a.scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    cast = R.load(a.roster).deliverable
    before = master_digests(root, [c.id for c in cast])
    print(f"masters before: {json.dumps(before, indent=2)}")

    results = []
    for ch in cast:
        print(f"\n=== {ch.id} ===")
        r = reexport(ch, server=a.server, root=root, input_dir=input_dir, scratch=scratch)
        print(f"  {r.get('skipped') or r['polarity']}; {len(r.get('tokens', {}))} tokens")
        results.append(r)

    after = master_digests(root, [c.id for c in cast])
    if before != after:
        raise SystemExit(f"MASTERS CHANGED -- before {before} after {after}")
    print(f"\nmasters unchanged ({len(after)} checked)")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
