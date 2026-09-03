#!/usr/bin/env python3
"""Letterbox CLIP + PickScore for a list of stills against their prompts -- the still stage's cull
signal (WI 1177). Whole-frame (letterbox) treatment only: WI 1045 measured it as the corrected
treatment; nothing of a 16:9 frame is discarded.

Input: a JSON file `[{"path": ..., "prompt": ...}, ...]`. Output (printed, and -o):

    {"scores": {<path>: {"clip_letterbox": x, "pickscore_letterbox": y}},
     "controls": {"clip_deterministic": bool, "pickscore_deterministic": bool},
     "versions": {"clip": "openai/clip-vit-base-patch32", "pickscore": "yuvalkirstain/PickScore_v1"}}

Run with the track-local scoring venv:  scoring/.venv/bin/python scoring/score_stills.py items.json -o out.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score as S  # noqa: E402  (frame_variants + the cosine scorer; heavy imports inside)

VERSIONS = {"clip": "openai/clip-vit-base-patch32", "pickscore": "yuvalkirstain/PickScore_v1"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("items", help="JSON list of {path, prompt}")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()
    items = json.loads(Path(args.items).read_text())

    from transformers import AutoModel, AutoProcessor, CLIPModel, CLIPProcessor
    clip = S._cosine_scorer(CLIPModel.from_pretrained(VERSIONS["clip"]).eval(),
                            CLIPProcessor.from_pretrained(VERSIONS["clip"]))
    pick = S._cosine_scorer(AutoModel.from_pretrained(VERSIONS["pickscore"]).eval(),
                            AutoProcessor.from_pretrained("laion/CLIP-ViT-H-14-laion2B-s32B-b79K"))

    scores, controls = {}, {}
    for i, it in enumerate(items):
        lb = S.frame_variants(Path(it["path"]))["letterbox"]
        c = round(clip(it["prompt"], lb), 4)
        p = round(pick(it["prompt"], lb), 4)
        if i == 0:
            controls["clip_deterministic"] = (round(clip(it["prompt"], lb), 4) == c)
            controls["pickscore_deterministic"] = (round(pick(it["prompt"], lb), 4) == p)
        scores[it["path"]] = {"clip_letterbox": c, "pickscore_letterbox": p}
        print(f"{Path(it['path']).name}: clip {c} pick {p}", file=sys.stderr, flush=True)
    out = {"scores": scores, "controls": controls, "versions": VERSIONS}
    text = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
