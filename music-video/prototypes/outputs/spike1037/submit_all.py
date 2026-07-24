#!/usr/bin/env python3
"""WI 1037: batch-SUBMIT every candidate prompt to ai2, then exit. Fetch separately (fetch_all.py).

On a shared, flaky-client box the per-job submit->wait->download loop only advances one job before a
dying client strands the rest. Submitting is fast and stateless: POST all prompts, record their ids,
let ai2 render them, and recover the outputs from /history afterwards (the WI 1020 server-state rule).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # prototypes/
import comfy_client
import generate_song as gsong
import generate_still as gstill

SERVER = "http://ai2:8188"
HERE = Path(__file__).resolve().parent
STILLS = HERE / "stills"
SONGS = HERE / "songs"

STYLE = ("painterly tabletop RPG concept art, dramatic volumetric light, warm lantern glow against "
         "cool blue shadows, cinematic wide establishing shot, richly detailed, muted desaturated "
         "palette, moody atmospheric")
SHOT_PROMPTS = {
    "shot4": ("two survivors inside a dark ruined building, one holding up a burning red flare that "
              "casts dramatic light, a menacing shadow looming in a broken stairwell behind them, "
              "tense, " + STYLE),
    "shot7": ("dawn breaking over a ruined city as silhouetted survivors walk away toward a fortified "
              "colony gate glowing with warm safe light, hope and resolution, wide cinematic vista, "
              + STYLE),
}
SEEDS = [41, 42, 43, 44, 45]
SANITY = ("a sunny tropical beach with palm trees and turquoise water, bright cheerful summer vacation, "
          "people relaxing on the sand, vibrant saturated colours, clear blue sky")
SONG_SEEDS = [702, 703, 704]


def main():
    submitted = []  # {kind, name, dest, prefix, pid}
    preset = gstill.MODELS["base"]

    def submit_still(name, prompt, seed):
        prefix = f"asset_harness/spike1037_{name}"
        graph = gstill.build_graph(prompt, gstill.DEFAULT_NEGATIVE, width=1280, height=720, seed=seed,
                                   model="base", steps=preset["steps"], cfg=preset["cfg"], prefix=prefix)
        pid = comfy_client.queue(SERVER, graph)
        submitted.append({"kind": "images", "name": name, "dest": str(STILLS / f"{name}.png"),
                          "prefix": f"spike1037_{name}", "pid": pid})
        print(f"submitted {name} pid={pid[:8]}")

    for shot, prompt in SHOT_PROMPTS.items():
        for s in SEEDS:
            submit_still(f"{shot}_seed{s}", prompt, s)
    submit_still("sanity_offbrief_seed41", SANITY, 41)

    for seed in SONG_SEEDS:
        name = f"clamor_hold_the_line_seed{seed}"
        graph = gsong.build_graph(gsong.SONG, seed, f"asset_harness/mv_{name}")
        pid = comfy_client.queue(SERVER, graph)
        submitted.append({"kind": "audio", "name": name, "dest": str(SONGS / f"{name}.flac"),
                          "prefix": f"mv_{name}", "pid": pid})
        print(f"submitted {name} pid={pid[:8]}")

    (HERE / "submitted.json").write_text(json.dumps(submitted, indent=2))
    print(f"\n{len(submitted)} prompts submitted -> submitted.json ; run fetch_all.py once ai2 drains")


if __name__ == "__main__":
    main()
