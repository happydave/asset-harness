#!/usr/bin/env python3
"""Audiobox Aesthetics scores for a set of songs -- the song stage's selector signal (WI 1176).

Audiobox only: the design rejected CLAP as a selector (WI 1045 measured it unable to separate
same-brief candidates) and its model load is the expensive part of score.py. Uses the decoded-tensor
path score.py established (its file reader links a CUDA library absent here), runs the determinism
control on the first file, and prints one JSON object:

    {"scores": {<stem>: {"CE":..,"CU":..,"PC":..,"PQ":..}}, "controls": {"audiobox_deterministic": bool},
     "version": "<audiobox_aesthetics version>", "seconds": {<stem>: wall-clock}}

Run with the track-local scoring venv:  scoring/.venv/bin/python scoring/score_audiobox.py a.flac b.flac -o out.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402  (its _load_mono; heavy imports stay inside functions)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--out", default=None, help="write the JSON here as well as printing it")
    args = ap.parse_args()

    import numpy as np
    import torch
    from audiobox_aesthetics.infer import initialize_predictor
    try:
        from importlib.metadata import version
        ver = version("audiobox_aesthetics")
    except Exception:
        ver = "unknown"
    pred = initialize_predictor()

    def aes(y, sr):
        wav = torch.from_numpy(np.ascontiguousarray(y)).unsqueeze(0)
        out = pred.forward([{"path": wav, "sample_rate": sr}])[0]
        return {k: round(float(v), 4) for k, v in out.items()}

    scores, secs, controls = {}, {}, {}
    for i, f in enumerate(args.files):
        p = Path(f)
        y, _ = score._load_mono(p)
        t0 = time.time()
        rec = aes(y, score.CLAP_SR)
        if i == 0:
            controls["audiobox_deterministic"] = (aes(y, score.CLAP_SR) == rec)
        secs[p.stem] = round(time.time() - t0, 1)
        scores[p.stem] = rec
    out = {"scores": scores, "controls": controls, "version": ver, "seconds": secs}
    text = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
