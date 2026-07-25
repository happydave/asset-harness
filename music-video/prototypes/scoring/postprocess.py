#!/usr/bin/env python3
"""Save-time post-processing for a generated song: apply the delivery ceiling + run the QC checks.

Split out from generate_song.py because it needs the scoring venv (numpy/scipy/soundfile) while the
generator itself runs under plain python3 (it only needs `requests`). generate_song invokes this with
the venv interpreter as a subprocess and parses the JSON it prints -- keeping the venv boundary clean.

    scoring/.venv/bin/python scoring/postprocess.py <file.flac> [--ceiling -1.0 | --no-ceiling]

Prints one JSON object: {ceiling?, truncated, end_decay_s, true_peak_dbtp}.
"""
import argparse
import json
from pathlib import Path

import audio_qc
import master


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--ceiling", type=float, default=-1.0)
    ap.add_argument("--no-ceiling", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    out = {}
    if not args.no_ceiling:
        out["ceiling"] = master.apply_ceiling(path, ceiling=args.ceiling)
    a = audio_qc.analyse(path)   # after any trim, so true_peak reflects the delivered file
    out["truncated"] = a["truncated"]
    out["end_decay_s"] = a["end_decay_s"]
    out["true_peak_dbtp"] = a["true_peak_dbtp"]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
