#!/usr/bin/env python3
"""WI 1637: a second stage over the adopted group-shot route's plate.

Two arms, because verifying the design's P4 showed the work item's proposal only half applies.

**Arm A — paste and correct.** The work item's proposal: put the master's own pixels into the
figure's place, then re-render at low denoise so they take the plate's light. It needs the plate's
figure and the master to agree on position, scale *and pose*. Route 3 got that free from its
ControlNet scaffold; regional conditioning does not supply it, so this runs on the half-orc alone —
the one figure whose plate pose is close to its master's — with a hand-measured box.

**Arm B — correct without pasting.** Re-render the region at low denoise with the character's own
tags and no master pixels. Pose-independent, needs no box and no matte. It is the same operation
as arm A minus the paste, so running both is also arm A's control: if B recovers the features, the
paste is doing nothing.

Masks are the whole **region column**, not a figure box. Route 3's residue came from masking
tighter than the plate's figure; a column cannot leave residue outside itself.
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
import scene

# Hand-measured off the plate, once, by drawing the boxes and looking (see spike.md P4). Only the
# half-orc is measured because only the half-orc runs arm A.
#
# (centre x, head-top y, visible-bottom y) in scored-canvas pixels. The figure is cut off by the
# frame at the bottom, so its full height is inferred from the template's knee line at 0.73.
PLATE_HALFORC = {"cx": 336, "head_top": 58, "visible_bottom": scene.SCORE_H}
KNEE_FRACTION = 0.73

MASTERS = Path.home() / "wi1611" / "out_final"


def region_mask(cid: str, out_dir: Path, pad: int = 12) -> Path:
    """The whole region column, white on black."""
    f = next(c for c in scene.CAST if c.cid == cid)
    m = Image.new("RGB", (scene.SCORE_W, scene.SCORE_H), (0, 0, 0))
    x0 = max(0, round(f.x0 * scene.SCORE_W) - pad)
    x1 = min(scene.SCORE_W, round(f.x1 * scene.SCORE_W) + pad)
    m.paste((255, 255, 255), (x0, 0, x1, scene.SCORE_H))
    p = out_dir / f"colmask_{cid}.png"
    m.save(p)
    return p


def paste_halforc(plate_path: Path, out_dir: Path) -> Path:
    """Arm A's input: the master laid over the plate's half-orc at the measured position."""
    plate = Image.open(plate_path).convert("RGBA")
    cut = composite.load_cutout(MASTERS / "derivatives" / "halforc" / "halforc.matte.png")

    visible = PLATE_HALFORC["visible_bottom"] - PLATE_HALFORC["head_top"]
    full_h = round(visible / KNEE_FRACTION)
    full_w = round(cut.width * full_h / cut.height)
    cut = cut.resize((full_w, full_h), Image.LANCZOS)

    plate.paste(cut, (round(PLATE_HALFORC["cx"] - full_w / 2), PLATE_HALFORC["head_top"]), cut)
    p = out_dir / "armA_pasted.png"
    plate.convert("RGB").save(p)
    return p


def tags_for(cid: str) -> str:
    f = next(c for c in scene.CAST if c.cid == cid)
    return f"{scene.QUALITY}, {f.tags}, {scene.SETTING}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:7126")
    a = ap.parse_args()

    out, input_dir = Path(a.out), Path(a.input_dir)
    out.mkdir(parents=True, exist_ok=True)
    plate = Path(a.plate)
    log = []

    def stage(name, graph):
        got = cc.run_job(a.server, graph, out / name, label=name)
        if not got:
            raise SystemExit(f"{name}: no image")
        log.append({"name": name, "path": str(got[0])})
        (out / "log.json").write_text(json.dumps(log, indent=2))
        return Path(got[0])

    def publish(p: Path, name: str) -> str:
        shutil.copy2(p, input_dir / name)
        return name

    plate_in = publish(plate, "c_plate.png")

    # --- arm A: paste, then correct -----------------------------------------------------------
    pasted = paste_halforc(plate, out)
    pasted_in = publish(pasted, "c_armA_pasted.png")
    mask_ho = publish(region_mask("halforc", out), "c_mask_halforc.png")
    for dn in (0.20, 0.30, 0.40):
        stage(f"armA_halforc_d{int(dn*100)}",
              graphs.region_inpaint(5101, f"wi1637/armA_d{int(dn*100)}", pasted_in, mask_ho,
                                    tags_for("halforc"), dn))

    # --- arm B: correct from tags, no paste ---------------------------------------------------
    for cid in ("halforc", "tiefling"):
        mk = publish(region_mask(cid, out), f"c_mask_{cid}.png")
        for dn in (0.20, 0.30, 0.40):
            stage(f"armB_{cid}_d{int(dn*100)}",
                  graphs.region_inpaint(5101, f"wi1637/armB_{cid}_d{int(dn*100)}", plate_in, mk,
                                        tags_for(cid), dn))

    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
