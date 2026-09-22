#!/usr/bin/env python3
"""Re-judge an existing run root by pixels: for every character, did each stage change the picture?

    python3 compare_stages.py --root ~/wi1611/out_final

Reads `masters/` and `derivatives/` only; writes nothing. Judged by decoded pixels: ComfyUI embeds
each stage's graph in the PNG, so file bytes never compare equal even when the picture did not
change. The chain order is the harness's; a stage file that is missing is reported, not skipped
silently.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chain
import provenance as P

ORDER = ("upscale", "face", "hand", "style", "matte")


def judge(root: Path, cid: str) -> list[tuple[str, str]]:
    rows = []
    prev = P.master_path(root, cid)
    for stage in ORDER:
        cur = P.derivative_path(root, cid, stage)
        if not cur.exists():
            rows.append((stage, "MISSING"))
            continue
        if not prev.exists():
            rows.append((stage, f"no input to compare ({prev.name} missing)"))
        else:
            try:
                inert = chain.is_inert(prev.read_bytes(), cur.read_bytes())
            except ValueError as e:
                rows.append((stage, f"ERROR {e}")); prev = cur; continue
            rows.append((stage, "INERT (pixels identical to input)" if inert else "changed"))
        prev = cur
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    ids = sorted(p.name[: -len(P.MASTER_SUFFIX)] for p in (root / P.MASTERS_DIR).glob(f"*{P.MASTER_SUFFIX}"))
    if not ids:
        raise SystemExit(f"no masters under {root / P.MASTERS_DIR}")
    inert_total = 0
    for cid in ids:
        print(f"{cid}:")
        for stage, verdict in judge(root, cid):
            print(f"  {stage:<8} {verdict}")
            inert_total += verdict.startswith("INERT")
    print(f"\n{len(ids)} characters, {inert_total} inert stage(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
