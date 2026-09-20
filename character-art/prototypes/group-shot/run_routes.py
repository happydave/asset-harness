#!/usr/bin/env python3
"""Drive the four group-shot routes over one scene, on one checkpoint, at matched settings.

Runs on `ai2` inside the WI 1626 container (`run_container.sh`). Each route writes into its own
directory under the run root, and every job's output stays on disk so a stage can be inspected
without re-running the route that produced it.

    python3 run_routes.py --root out --input-dir ~/wi1626/input --server http://127.0.0.1:7126

Route selection is explicit (`--routes 1,2,3,4`) because the routes have very different costs and
a failure in one should not cost the others a re-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

import comfy_client as cc
import composite
import graphs
import pose
import scene

MASTERS = Path.home() / "wi1611" / "out_final"


def stage(server: str, graph: dict, out_stem: Path, label: str) -> Path:
    """One job. Returns the single image it produced, and fails loudly if it produced none --
    a stage that silently yields nothing is how a route gets scored on a stale file."""
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    got = cc.run_job(server, graph, out_stem, label=label)
    if not got:
        raise SystemExit(f"{label}: job produced no output")
    return got[0]


def publish(src: Path, input_dir: Path, name: str) -> str:
    """Copy an artifact into ComfyUI's input directory so a later graph can LoadImage it."""
    dest = input_dir / name
    shutil.copy2(src, dest)
    return name


def route1(server, root, input_dir, log):
    out = root / "route1"
    for seed in scene.SEEDS:
        raw = stage(server, graphs.route1_direct(seed, f"r1_{seed}"),
                    out / f"s{seed}_raw", f"r1 direct seed={seed}")
        name = publish(raw, input_dir, f"r1_{seed}_raw.png")
        up = stage(server, graphs.upscale_2x(name, f"r1_{seed}_up"),
                   out / f"s{seed}_scored", f"r1 upscale seed={seed}")
        log.append({"route": 1, "seed": seed, "scored": str(up)})


def route4(server, root, input_dir, log):
    out = root / "route4"
    for seed in scene.SEEDS:
        raw = stage(server, graphs.route4_regional(seed, f"r4_{seed}"),
                    out / f"s{seed}_raw", f"r4 regional seed={seed}")
        name = publish(raw, input_dir, f"r4_{seed}_raw.png")
        up = stage(server, graphs.upscale_2x(name, f"r4_{seed}_up"),
                   out / f"s{seed}_scored", f"r4 upscale seed={seed}")
        log.append({"route": 4, "seed": seed, "scored": str(up)})

    # FC1: same seed, regions widened to the full frame. Only the spatial information is removed.
    seed = scene.SEEDS[0]
    ctl = stage(server, graphs.route4_regional(seed, f"r4_{seed}_fc1", collapse=True),
                out / f"s{seed}_fc1_control", f"r4 FC1 control seed={seed}")
    log.append({"route": 4, "seed": seed, "control": "fc1_collapsed_regions", "scored": str(ctl)})


def route3(server, root, input_dir, log):
    out = root / "route3"
    out.mkdir(parents=True, exist_ok=True)

    scaffold = out / "scaffold.png"
    pose.party_scaffold(scene.GEN_W, scene.GEN_H, pose.PARTY_LAYOUT).save(scaffold)
    hint = publish(scaffold, input_dir, "r3_scaffold.png")

    seed = scene.SEEDS[0]
    posed = stage(server, graphs.route3_posed(seed, f"r3_{seed}", hint),
                  out / f"s{seed}_posed", f"r3 posed seed={seed}")
    pname = publish(posed, input_dir, f"r3_{seed}_posed.png")
    up = stage(server, graphs.upscale_2x(pname, f"r3_{seed}_up"),
               out / f"s{seed}_posed_scored", f"r3 upscale seed={seed}")
    log.append({"route": 3, "seed": seed, "phase": "posed", "scored": str(up)})

    # FC1: the scaffold is still loaded and still routed through ControlNet; only its influence
    # goes to zero.
    ctl = stage(server, graphs.route3_posed(seed, f"r3_{seed}_fc1", hint, strength=0.0),
                out / f"s{seed}_fc1_control", f"r3 FC1 control seed={seed}")
    log.append({"route": 3, "seed": seed, "control": "fc1_controlnet_strength_0",
                "scored": str(ctl)})

    # Second half: paste each master's cut-out into its region of the posed plate, then re-render
    # that region at low denoise so the pasted pixels take the plate's light. Same placement rule
    # as route 2, so the two routes' layouts are the same target.
    plate = Image.open(up).convert("RGBA")
    mattes = {f.cid: MASTERS / "derivatives" / f.cid / f"{f.cid}.matte.png" for f in scene.CAST}
    boxes = composite.paste_cast(plate, mattes)

    pasted = out / "pasted.png"
    plate.convert("RGB").save(pasted)
    masks = composite.write_masks(boxes, out)

    cur = publish(pasted, input_dir, "r3_pasted.png")
    for i, f in enumerate(scene.CAST):
        mname = publish(masks[f.cid], input_dir, f"r3_mask_{f.cid}.png")
        res = stage(server,
                    graphs.region_inpaint(seed + i, f"r3_inpaint_{f.cid}", cur, mname,
                                          f"{scene.QUALITY}, {f.tags}, {scene.SETTING}", 0.30),
                    out / f"inpaint_{f.cid}", f"r3 inpaint {f.cid}")
        cur = publish(res, input_dir, f"r3_after_{f.cid}.png")
    log.append({"route": 3, "seed": seed, "phase": "inpainted", "scored": str(res)})


def route2(server, root, input_dir, log):
    out = root / "route2"
    out.mkdir(parents=True, exist_ok=True)

    seed = scene.SEEDS[0]
    plate = stage(server, graphs.backdrop(seed, f"r2_bd_{seed}"),
                  out / "backdrop_raw", "r2 backdrop")
    bname = publish(plate, input_dir, "r2_backdrop_raw.png")
    plate_up = stage(server, graphs.upscale_2x(bname, "r2_bd_up"),
                     out / "backdrop_scored", "r2 backdrop upscale")

    mattes = {f.cid: MASTERS / "derivatives" / f.cid / f"{f.cid}.matte.png" for f in scene.CAST}
    comp = out / "composite.png"
    boxes = composite.build(plate_up, mattes, comp)
    (out / "boxes.json").write_text(json.dumps(boxes, indent=2))
    log.append({"route": 2, "phase": "composite_raw", "scored": str(comp)})

    cname = publish(comp, input_dir, "r2_composite.png")
    for dn in (0.20, 0.25):
        res = stage(server, graphs.unify(seed, f"r2_unify_{int(dn*100)}", cname, dn),
                    out / f"unified_{int(dn*100)}", f"r2 unify denoise={dn}")
        log.append({"route": 2, "phase": f"unified_d{dn}", "scored": str(res)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:7126")
    ap.add_argument("--routes", default="1,2,3,4")
    a = ap.parse_args()

    root, input_dir = Path(a.root), Path(a.input_dir)
    root.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    log: list[dict] = []
    fns = {"1": route1, "2": route2, "3": route3, "4": route4}
    for r in a.routes.split(","):
        print(f"=== route {r} ===", flush=True)
        fns[r.strip()](a.server, root, input_dir, log)
        (root / "runlog.json").write_text(json.dumps(log, indent=2))

    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
