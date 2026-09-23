#!/usr/bin/env python3
"""Write `recorded_recipes.json`: the generation recipe each frozen WI 1599 candidate carries in its
own `prompt` chunk, keyed by roster id.

    python3 extract_recipes.py CANDIDATES_DIR > recorded_recipes.json

The images are the authority, not the script that queued them: WI 1599 regenerated the dragonborn
from a second prompt (`dragonborn2`) that `gen_portraits.py` does not contain. Stops, writing
nothing, when a candidate is missing or carries no graph.
"""
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

#: Roster id -> the WI 1599 candidate frozen for it (WI 1599 spike, "Frozen inputs").
FROZEN = {
    "tiefling": "cand_tiefling_s303_00001_.png",
    "dragonborn": "cand_dragonborn2_s404_00001_.png",
    "halforc": "cand_halforc_s202_00001_.png",
    "human": "cand_human_s202_00001_.png",
}


def _node(graph: dict, cls: str) -> dict:
    found = [n for n in graph.values() if isinstance(n, dict) and n.get("class_type") == cls]
    if len(found) != 1:
        raise SystemExit(f"expected one {cls} node, found {len(found)}")
    return found[0]["inputs"]


def recipe(path: Path) -> dict:
    data = path.read_bytes()
    text = Image.open(path).info.get("prompt")
    if not text:
        raise SystemExit(f"{path}: no embedded prompt graph")
    graph = json.loads(text)
    ks = _node(graph, "KSampler")
    latent = _node(graph, "EmptyLatentImage")
    return {
        "source": path.name,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "ckpt": _node(graph, "CheckpointLoaderSimple")["ckpt_name"],
        "clip_skip": _node(graph, "CLIPSetLastLayer")["stop_at_clip_layer"],
        "seed": ks["seed"], "steps": ks["steps"], "cfg": ks["cfg"],
        "sampler": ks["sampler_name"], "scheduler": ks["scheduler"], "denoise": ks["denoise"],
        "width": latent["width"], "height": latent["height"],
        "positive": graph[str(ks["positive"][0])]["inputs"]["text"],
        "negative": graph[str(ks["negative"][0])]["inputs"]["text"],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    src = Path(argv[0])
    missing = [f for f in FROZEN.values() if not (src / f).is_file()]
    if missing:
        raise SystemExit(f"{src}: missing candidate(s): {', '.join(missing)}")
    out = {cid: recipe(src / name) for cid, name in FROZEN.items()}
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
