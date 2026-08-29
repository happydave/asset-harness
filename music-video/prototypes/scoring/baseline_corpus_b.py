#!/usr/bin/env python3
"""WI 1179: run the WI 1045 image scorers over corpus B, so the VLM has a like-for-like baseline.

The +0.30 PickScore figure the promotion bar refers to was measured on corpus A. Comparing a VLM's
corpus-B result against it would be comparing two different datasets, so the same scorers are run here
on the same images the judge sees. Letterbox treatment only — WI 1045 measured it as PickScore's best.

Run with the track-local scoring venv:  scoring/.venv/bin/python scoring/baseline_corpus_b.py
"""
import json
from pathlib import Path

import score as S          # WI 1045 harness: frame_variants + the cosine scorer

HERE = Path(__file__).resolve().parent
IMAGERY = HERE.parent / "outputs" / "scienceranch-imagery"
SEEDS = (101, 202, 303)
OUT = HERE / "baseline_corpus_b.json"


def main():
    prompts = json.loads((HERE / "corpus_b_prompts.json").read_text())
    from transformers import AutoModel, AutoProcessor, CLIPModel, CLIPProcessor

    clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    clip_score = S._cosine_scorer(clip, CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"))
    pick = AutoModel.from_pretrained("yuvalkirstain/PickScore_v1").eval()
    pick_score = S._cosine_scorer(pick, AutoProcessor.from_pretrained("laion/CLIP-ViT-H-14-laion2B-s32B-b79K"))

    out = {}
    for slot, prompt in prompts.items():
        scores = {}
        for seed in SEEDS:
            p = IMAGERY / f"{slot}_s{seed}.png"
            letterbox = S.frame_variants(p)["letterbox"]
            scores[p.name] = {"clip_letterbox": round(clip_score(prompt, letterbox), 4),
                              "pickscore_letterbox": round(pick_score(prompt, letterbox), 4)}
            print(f"{p.name}: {scores[p.name]}", flush=True)
        out[slot] = {"prompt": prompt, "scores": scores}
        for key in ("clip_letterbox", "pickscore_letterbox"):
            ranked = sorted(scores, key=lambda n: -scores[n][key])
            out[slot][f"order_{key}"] = ranked

    # Determinism control, same shape as WI 1045's: rescore one item and require an identical number.
    slot = sorted(prompts)[0]
    p = IMAGERY / f"{slot}_s101.png"
    again = round(pick_score(prompts[slot], S.frame_variants(p)["letterbox"]), 4)
    out["_control"] = {"rescored": p.name, "pickscore_letterbox": again,
                       "deterministic": again == out[slot]["scores"][p.name]["pickscore_letterbox"]}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"-> {OUT}  determinism: {out['_control']['deterministic']}")


if __name__ == "__main__":
    main()
