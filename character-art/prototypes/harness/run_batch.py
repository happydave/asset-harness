#!/usr/bin/env python3
"""Drive a roster CSV through the finishing chain to VTT tokens.

    python3 run_batch.py --roster roster/cast.csv --root out --server http://127.0.0.1:7124

Every write goes through provenance.write_guarded, so the master rule is enforced by the tooling
rather than by remembering it (WI 1611 AC3). Every stage records what it did on the character's
record, including what it skipped and why, so the run is auditable after the fact.

A detail stage is judged by two things the job hands back -- the detailed image and the detector's
mask -- and decided by `chain.detail_verdict`. Pixels are compared, never file bytes: ComfyUI writes
each stage's graph into the PNG, so bytes differ even when nothing was done (WI 1732).

A re-run over an existing root reuses the master (after checking the seed and prompt it carries
against the roster) and writes every new artifact to a versioned path beside the old one.

The ComfyUI round trip is injected (`run=`) so the whole driver runs under test with a fake runner;
`_run_job` is the production default.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import requests

import chain
import comfy_client as cc
import provenance as P
import roster as R
from PIL import Image

#: What a character's failure is allowed to be. Anything else is a bug in the driver and propagates.
CHARACTER_FAILURES = (SystemExit, PermissionError, ValueError)


def _run_job(server, graph, label, work: Path) -> list[Path]:
    """Queue `graph`, wait for its terminal state, download every image it produced.

    Each local copy is named after the filename ComfyUI reports for it, so a stage that saves two
    images (the detail pass and its mask) hands back two distinguishable files. An empty output
    list is a failure, not an empty success -- ComfyUI has been seen to report success with none.
    """
    pid = cc.queue(server, graph)
    hist = cc.wait_for_history(server, pid, label=label)
    work.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for node in hist.get("outputs", {}).values():
        for item in node.get("images", []):
            r = requests.get(f"{server.rstrip('/')}/view",
                             params={"filename": item["filename"],
                                     "subfolder": item.get("subfolder", ""),
                                     "type": item.get("type", "output")}, timeout=600)
            r.raise_for_status()
            p = work / Path(item["filename"]).name   # never let a reported name pick a directory
            p.write_bytes(r.content)
            saved.append(p)
    if not saved:
        raise SystemExit(f"stage produced no image (reported success with empty outputs): {label}")
    return saved


def _stage_into_input(src: Path, input_dir: Path, name: str) -> str:
    """Copy a produced image into ComfyUI's input dir so the next stage can LoadImage it."""
    dest = input_dir / name
    shutil.copyfile(src, dest)
    return name


def _one(outputs: list[Path], label: str) -> Path:
    if len(outputs) != 1:
        raise SystemExit(f"{label}: expected one image, got {len(outputs)}: "
                         f"{[p.name for p in outputs]}")
    return outputs[0]


def _split_detail_outputs(outputs: list[Path], label: str, prefix: str) -> tuple[Path, Path]:
    """(detailed image, mask) from a detail job's outputs, told apart by ComfyUI's filename.

    `prefix` is the graph's filename prefix without its directory; the mask's name starts with
    `prefix + MASK_SUFFIX + "_"`, the image's with `prefix + "_"`. Matched on the whole prefix so a
    character id that itself contains "_mask" cannot confuse the two.
    """
    base = Path(prefix).name
    masks = [p for p in outputs if p.name.startswith(f"{base}{chain.MASK_SUFFIX}_")]
    images = [p for p in outputs if p not in masks and p.name.startswith(f"{base}_")]
    if len(masks) != 1 or len(images) != 1:
        raise SystemExit(f"{label}: expected one image and one mask, got "
                         f"{[p.name for p in outputs]}")
    return images[0], masks[0]


def master_negative(ch: R.Character) -> str:
    """The negative a master is made with: the row's, or the harness default when the row has none."""
    return ch.negative or chain.NEG


def reuse_or_make_master(ch: R.Character, *, server, root: Path, work: Path, record: dict,
                         run) -> bytes:
    """The master's bytes: read from an existing master, or generated and written once.

    An existing master is never regenerated (I1 makes it unwritable anyway). Before it is reused,
    the seed, prompt and negative it carries are compared with the roster row's; a master made from
    a different recipe must not front this run. A master with no embedded graph is reused with the
    absence recorded.
    """
    master = P.master_path(root, ch.id)
    negative = master_negative(ch)
    record["master"] = str(master)
    if master.exists():
        data = master.read_bytes()
        record["master_reused"] = True
        recipe = chain.embedded_recipe(data)
        if recipe is None:
            record["master_provenance"] = "absent"
        else:
            record["master_provenance"] = recipe
            mismatch = []
            if recipe.get("seed") != ch.seed:
                mismatch.append(f"seed: master {recipe.get('seed')!r}, roster {ch.seed!r}")
            if recipe.get("prompt") != ch.tags:
                mismatch.append(f"prompt: master {recipe.get('prompt')!r}, roster {ch.tags!r}")
            if recipe.get("negative") != negative:
                mismatch.append(f"negative: master {recipe.get('negative')!r}, roster {negative!r}")
            if mismatch:
                raise SystemExit(f"{ch.id}: existing master was not made from this roster row -- "
                                 + "; ".join(mismatch)
                                 + ". Move it aside or run into a fresh root.")
        return data

    produced = _one(run(server, chain.generate(ch.tags, ch.seed, f"wi1611/{ch.id}_master",
                                               negative=negative),
                        f"{ch.id}:generate", work / "master"), f"{ch.id}:generate")
    data = produced.read_bytes()
    P.write_guarded(master, P.ROLE_MASTER, data)
    record["master_reused"] = False
    return data


def process(ch: R.Character, *, server, root: Path, input_dir: Path, scratch: Path,
            style_denoise: float, record: dict, run=_run_job) -> dict:
    prompt = ch.tags
    work = scratch / ch.id
    work.mkdir(parents=True, exist_ok=True)

    # --- stage 0: the master -----------------------------------------------------------------
    cur_bytes = reuse_or_make_master(ch, server=server, root=root, work=work, record=record, run=run)
    record["stages"] = []
    master_copy = work / "master.png"
    master_copy.write_bytes(cur_bytes)
    cur_name = _stage_into_input(master_copy, input_dir, f"{ch.id}_master.png")

    def dest_for(path: Path) -> Path:
        return P.versioned(path)

    def write_stage(name: str, data: bytes, entry: dict, out: Path):
        nonlocal cur_name, cur_bytes
        dest = dest_for(P.derivative_path(root, ch.id, name))
        P.write_guarded(dest, name, data)
        entry["path"] = str(dest)
        record["stages"].append(entry)
        cur_name = _stage_into_input(out, input_dir, f"{ch.id}_{name}.png")
        cur_bytes = data

    def stage(name, graph, *, cutout_required=False):
        out = _one(run(server, graph, f"{ch.id}:{name}", work / name), f"{ch.id}:{name}")
        data = out.read_bytes()
        entry = {"stage": name, "pixels_changed": not chain.is_inert(cur_bytes, data),
                 "sha": chain.digest(data)}
        if cutout_required and not chain.figure_is_opaque(data):
            # The matte's polarity is the one stage failure no later check can see (WI 1636).
            entry["error"] = f"matte is not a figure-opaque cut-out -- {chain.explain_alpha(data)}"
            record["stages"].append(entry)
            raise SystemExit(f"{ch.id}: {entry['error']}")
        write_stage(name, data, entry, out)
        return out

    def detail_stage(name, detector):
        """A detail pass: judged by what the detector found and what the pixels did (I4)."""
        prefix = f"wi1611/{ch.id}_{name}"
        graph = chain.detail(cur_name, detector, prompt, ch.seed, prefix)
        image, mask = _split_detail_outputs(run(server, graph, f"{ch.id}:{name}", work / name),
                                            f"{ch.id}:{name}", prefix)
        data = image.read_bytes()
        detected = chain.mask_detected(mask.read_bytes())
        changed = not chain.is_inert(cur_bytes, data)
        verdict = chain.detail_verdict(detected, changed)
        entry = {"stage": name, "detected": detected, "pixels_changed": changed,
                 "outcome": verdict.outcome, "reason": verdict.reason, "sha": chain.digest(data)}
        if verdict.outcome == "fail":
            entry["error"] = verdict.reason
            record["stages"].append(entry)
            raise SystemExit(f"{ch.id}: {name} -- {verdict.reason}")
        write_stage(name, data, entry, image)
        return image

    stage("upscale", chain.upscale(cur_name, f"wi1611/{ch.id}_upscale"))
    detail_stage("face", chain.FACE_DETECTOR)
    detail_stage("hand", chain.HAND_DETECTOR)
    stage("style", chain.house_style(cur_name, prompt, ch.seed, f"wi1611/{ch.id}_style",
                                     style_denoise))
    matted = stage("matte", chain.matte(cur_name, f"wi1611/{ch.id}_matte"),
                   cutout_required=True)

    # --- tokens ------------------------------------------------------------------------------
    if ch.targets:
        written = tokens_export(matted, root, ch, dest_for)
        record["tokens"] = {k: str(v) for k, v in written.items()}
    else:
        record["tokens"] = {}
        record.setdefault("notes", []).append("no delivery targets requested")
    return record


def tokens_export(matted: Path, root: Path, ch: R.Character, dest_for):
    import tokens as T
    with Image.open(matted) as im:
        return T.export(im, root, ch.id, ch.targets, dest_for=dest_for)


def main(argv=None, run=_run_job):
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", required=True)
    ap.add_argument("--root", required=True, help="output root; masters/ and derivatives/ live here")
    ap.add_argument("--server", default="http://127.0.0.1:7124")
    ap.add_argument("--input-dir", required=True, help="ComfyUI's input directory")
    ap.add_argument("--scratch", default="/tmp/wi1611")
    ap.add_argument("--style-denoise", type=float, default=0.25,
                    help="house-style pass denoise; design D3 declines to inherit 0.20-0.30 "
                         "unmeasured, so this is explicit")
    ap.add_argument("--only", help="comma-separated character ids")
    args = ap.parse_args(argv)

    load = R.load(args.roster)
    print("roster:"); print(R.report(load))
    todo = load.deliverable
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        todo = [c for c in todo if c.id in want]
    if not todo:
        raise SystemExit("nothing deliverable to run")

    root = Path(args.root); input_dir = Path(args.input_dir); scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    failures = []
    for ch in todo:
        print(f"\n=== {ch.id} ({ch.display_name}) ===")
        rec = {"id": ch.id, "display_name": ch.display_name,
               "identity_features": ch.identity_features, "tier": ch.tier, "seed": ch.seed,
               "style_denoise": args.style_denoise, "house_style_lora": None}
        try:
            process(ch, server=args.server, root=root, input_dir=input_dir, scratch=scratch,
                    style_denoise=args.style_denoise, record=rec, run=run)
            skipped = [s["stage"] for s in rec.get("stages", []) if s.get("outcome") == "skip"]
            print(f"  done: {len(rec.get('stages', []))} stages, "
                  f"{len(rec.get('tokens', {}))} tokens"
                  + (f", skipped: {', '.join(skipped)}" if skipped else ""))
        except CHARACTER_FAILURES as e:
            # One character's failure must not cost the rest of the batch their GPU time -- and
            # the guard's refusal is a failure of that character, not of the run (WI 1732).
            rec["failed"] = str(e)
            failures.append(ch.id)
            print(f"  FAILED: {e}")
        records[ch.id] = rec

    rec_path = P.versioned(root / "records.json")
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nrecords -> {rec_path}")
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
