#!/usr/bin/env python3
"""The roster regenerates what it says it does (WI 1642). Plain `python3 test_cast_recipes.py`.

`roster/recorded_recipes.json` holds the recipe each frozen WI 1599 candidate carries in its own
embedded graph (written by `roster/extract_recipes.py`, never by hand). For every entry, the master
graph the harness builds from the roster row with that id must carry exactly that recipe.
"""
import json
import sys
from pathlib import Path

import chain
import roster as R
import run_batch as RB

HERE = Path(__file__).resolve().parent
ROSTER = HERE.parent.parent / "roster" / "cast.csv"
RECIPES = HERE.parent.parent / "roster" / "recorded_recipes.json"

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def one(graph: dict, cls: str) -> dict:
    nodes = [n for n in graph.values() if n["class_type"] == cls]
    assert len(nodes) == 1, (cls, len(nodes))
    return nodes[0]["inputs"]


def built(ch: R.Character) -> dict:
    """The recipe fields of the master graph the harness would queue for this row."""
    g = chain.generate(ch.tags, ch.seed, "x", negative=RB.master_negative(ch))
    ks = one(g, "KSampler")
    latent = one(g, "EmptyLatentImage")
    return {
        "ckpt": one(g, "CheckpointLoaderSimple")["ckpt_name"],
        "clip_skip": one(g, "CLIPSetLastLayer")["stop_at_clip_layer"],
        "seed": ks["seed"], "steps": ks["steps"], "cfg": ks["cfg"],
        "sampler": ks["sampler_name"], "scheduler": ks["scheduler"], "denoise": ks["denoise"],
        "width": latent["width"], "height": latent["height"],
        "positive": g[str(ks["positive"][0])]["inputs"]["text"],
        "negative": g[str(ks["negative"][0])]["inputs"]["text"],
    }


def main():
    print("the roster against WI 1599's recorded recipes")
    recipes = json.loads(RECIPES.read_text(encoding="utf-8"))
    load = R.load(ROSTER)
    by_id = {c.id: c for c in load.characters}

    for cid, want in recipes.items():
        ch = by_id.get(cid)
        check(f"{cid}: a roster row exists for the recorded recipe", ch is not None, sorted(by_id))
        if ch is None:
            continue
        got = built(ch)
        for key, value in got.items():
            check(f"{cid}: {key} equals the recorded {key}", value == want[key],
                  f"built {value!r}, recorded {want[key]!r}")

    # A row that claims WI 1599 without a recipe to hold it to is the drift this test exists for.
    for c in load.characters:
        if "WI 1599" in c.extra.get("notes", ""):
            check(f"{c.id}: its WI 1599 claim has a recorded recipe", c.id in recipes)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
