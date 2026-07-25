#!/usr/bin/env python3
"""Score an arbitrary set of songs with the corrected audio scorers (WI 1045's score_audio).

Built for WI 1043: the base-vs-turbo checkpoint race is the first song set with REAL quality variance
(WI 1037's four candidates shared one checkpoint and one tag string, so no scorer had anything to
discriminate). Machine scores here are a SECOND TRIAL alongside the owner's ear, never the authority --
the vocal-quality verdict is a [human] criterion.

  scoring/.venv/bin/python scoring/score_songs.py <dir-of-flacs> [-o out.json]
"""
import argparse
import json
from pathlib import Path

import score


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("songs_dir")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    d = Path(args.songs_dir)
    songs = {p.stem: p for p in sorted(d.glob("*.flac"))}
    if not songs:
        raise SystemExit(f"no .flac files in {d}")
    print(f"scoring {len(songs)} songs from {d}")

    controls = {}
    result = score.score_audio(controls, songs=songs)
    result["controls"] = controls
    out = Path(args.out) if args.out else d.parent / "machine_scores_songs.json"
    out.write_text(json.dumps(result, indent=2))

    print("\ndeterminism controls:")
    for k, v in sorted(controls.items()):
        print(f"  {k:26s} {v}")
    for rk in sorted(k for k in result if k.startswith("rank_")):
        order = [n for n, _ in sorted(result[rk].items(), key=lambda kv: kv[1])]
        print(f"{rk:22s} best -> worst: {', '.join(order)}")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
