#!/usr/bin/env python3
"""WI 1037 spike: generate still candidate sets (seed sweeps) + one off-brief sanity-floor.

Two real shots from the WI 1004 lobby (flare/stairwell + dawn-resolve) each get a 5-seed sweep so the
scorers and the owner have visibly-different candidates to rank; one deliberately off-brief image
(tropical beach) is the sanity floor -- it MUST rank last for a zombie-survival video under both the
scorers and the owner.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # prototypes/ on path
import comfy_client
import generate_still as gs

SERVER = "http://ai2:8188"
OUT = Path(__file__).resolve().parent / "stills"
OUT.mkdir(parents=True, exist_ok=True)

STYLE = ("painterly tabletop RPG concept art, dramatic volumetric light, warm lantern glow against "
         "cool blue shadows, cinematic wide establishing shot, richly detailed, muted desaturated "
         "palette, moody atmospheric")

SHOTS = {
    "shot4": ("two survivors inside a dark ruined building, one holding up a burning red flare that "
              "casts dramatic light, a menacing shadow looming in a broken stairwell behind them, "
              "tense, " + STYLE),
    "shot7": ("dawn breaking over a ruined city as silhouetted survivors walk away toward a fortified "
              "colony gate glowing with warm safe light, hope and resolution, wide cinematic vista, "
              + STYLE),
}
SEEDS = [41, 42, 43, 44, 45]
# Deliberately off-brief: wrong genre/mood entirely. Sanity floor.
SANITY = ("a sunny tropical beach with palm trees and turquoise water, bright cheerful summer vacation, "
          "people relaxing on the sand, vibrant saturated colours, clear blue sky")


def gen(prompt, out_stem, seed):
    if Path(str(out_stem) + ".png").exists():
        print(f"skip {out_stem.name} (exists)"); return
    preset = gs.MODELS["base"]
    graph = gs.build_graph(prompt, gs.DEFAULT_NEGATIVE, width=1280, height=720, seed=seed,
                           model="base", steps=preset["steps"], cfg=preset["cfg"],
                           prefix=f"asset_harness/spike1037_{out_stem.name}")
    print(f"gen {out_stem.name} (seed {seed}) ...", flush=True)
    got = comfy_client.run_job(SERVER, graph, out_stem, kinds=("images",), label=out_stem.name)[0]
    print(f"  -> {got.name}")


def main():
    for shot, prompt in SHOTS.items():
        for s in SEEDS:
            gen(prompt, OUT / f"{shot}_seed{s}", s)
    gen(SANITY, OUT / "sanity_offbrief_seed41", 41)
    print("done")


if __name__ == "__main__":
    main()
