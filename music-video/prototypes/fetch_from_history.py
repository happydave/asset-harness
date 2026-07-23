#!/usr/bin/env python3
"""Recover a completed ComfyUI prompt's outputs AFTER THE FACT, from /history.

Use when a client exited before downloading (e.g. a backstop was hit, or the process was killed) but
the job finished server-side. The output is still in ComfyUI's history until it rolls off. This is the
WI 1018 ad-hoc recovery made a first-class tool — so a finished job is never lost.

  # by prompt_id (printed by the client / found in the journal):
  fetch_from_history.py --pid 145d2f74-... --out ./recovered_clip
  # or by newest output whose filename contains a substring:
  fetch_from_history.py --filename mv_clip --out ./recovered_clip
"""
from __future__ import annotations

import argparse

import comfy_client


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    ap.add_argument("--pid", default=None, help="exact prompt_id to recover")
    ap.add_argument("--filename", default=None,
                    help="substring of an output filename; recovers the newest match")
    ap.add_argument("--out", required=True, help="output path stem")
    ap.add_argument("--index", type=int, default=-1,
                    help="which match when using --filename (default -1 = newest)")
    args = ap.parse_args()
    if not args.pid and not args.filename:
        raise SystemExit("give --pid or --filename")

    paths = comfy_client.fetch_from_history(
        args.server, out_stem=args.out, pid=args.pid,
        filename_substr=args.filename, index=args.index)
    for p in paths:
        print(f"-> {p}")


if __name__ == "__main__":
    main()
