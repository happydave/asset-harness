#!/usr/bin/env python3
"""Drive a roster CSV through the finishing chain to VTT tokens.

    python3 run_batch.py --roster roster/cast.csv --root out --server http://127.0.0.1:7124

Every write goes through provenance.write_guarded, so the master rule is enforced by the tooling
rather than by remembering it (WI 1611 AC3). Every stage records what it did on the character's
record, including what it skipped and why, so the run is auditable after the fact.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import chain
import comfy_client as cc
import provenance as P
import roster as R
from PIL import Image

def _fetch_one(server, hist, dest_stem: Path) -> Path:
    """Download the single image a stage produced. An empty output list is a failure, not an
    empty success -- ComfyUI has been seen to report success with no image."""
    got = cc.download_outputs(server, hist, dest_stem, kinds=("images",))
    paths = [Path(p) for p in (got or [])]
    if not paths:
        raise SystemExit(f"stage produced no image (reported success with empty outputs): {dest_stem}")
    return paths[0]


def _run(server, graph, label, stem: Path) -> Path:
    pid = cc.queue(server, graph)
    hist = cc.wait_for_history(server, pid, label=label)
    return _fetch_one(server, hist, stem)


def _stage_into_input(src: Path, input_dir: Path, name: str) -> str:
    """Copy a produced image into ComfyUI's input dir so the next stage can LoadImage it."""
    dest = input_dir / name
    shutil.copyfile(src, dest)
    return name


def process(ch: R.Character, *, server, root: Path, input_dir: Path, scratch: Path,
            style_denoise: float, record: dict) -> dict:
    prompt = ch.tags
    work = scratch / ch.id
    work.mkdir(parents=True, exist_ok=True)

    # --- stage 0: the master -----------------------------------------------------------------
    produced = _run(server, chain.generate(prompt, ch.seed, f"wi1611/{ch.id}_master"),
                    f"{ch.id}:generate", work / "master")
    master = P.master_path(root, ch.id)
    P.write_guarded(master, P.ROLE_MASTER, produced.read_bytes())
    record["master"] = str(master)
    record["stages"] = []
    cur_name = _stage_into_input(produced, input_dir, f"{ch.id}_master.png")
    cur_bytes = produced.read_bytes()

    def stage(name, graph, *, diff_required=False):
        nonlocal cur_name, cur_bytes
        out = _run(server, graph, f"{ch.id}:{name}", work / name)
        data = out.read_bytes()
        changed = not chain.is_inert(cur_bytes, data)
        entry = {"stage": name, "changed": changed, "sha": chain.digest(data)}
        if diff_required and not changed:
            # I4: a detail pass whose detector did not load runs, reports success, and changes
            # nothing. A bit-identical output is that failure's observable.
            entry["error"] = "output identical to input -- detector did not fire or did not load"
            record["stages"].append(entry)
            raise SystemExit(
                f"{ch.id}: {name} produced a bit-identical image. A FaceDetailer without a loaded "
                f"UltralyticsDetectorProvider is silently inert; refusing to treat that as success.")
        dest = P.derivative_path(root, ch.id, name)
        P.write_guarded(dest, name, data)
        entry["path"] = str(dest)
        record["stages"].append(entry)
        cur_name = _stage_into_input(out, input_dir, f"{ch.id}_{name}.png")
        cur_bytes = data
        return out

    stage("upscale", chain.upscale(cur_name, f"wi1611/{ch.id}_upscale"))
    stage("face", chain.detail(cur_name, chain.FACE_DETECTOR, prompt, ch.seed,
                               f"wi1611/{ch.id}_face"), diff_required=True)
    stage("hand", chain.detail(cur_name, chain.HAND_DETECTOR, prompt, ch.seed,
                               f"wi1611/{ch.id}_hand"))
    stage("style", chain.house_style(cur_name, prompt, ch.seed, f"wi1611/{ch.id}_style",
                                     style_denoise))
    matted = stage("matte", chain.matte(cur_name, f"wi1611/{ch.id}_matte"))

    # --- tokens ------------------------------------------------------------------------------
    if ch.targets:
        written = tokens_export(matted, root, ch)
        record["tokens"] = {k: str(v) for k, v in written.items()}
    else:
        record["tokens"] = {}
        record.setdefault("notes", []).append("no delivery targets requested")
    return record


def tokens_export(matted: Path, root: Path, ch: R.Character):
    import tokens as T
    with Image.open(matted) as im:
        return T.export(im, root, ch.id, ch.targets)


def main():
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
    args = ap.parse_args()

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
    records = {}
    failures = []
    for ch in todo:
        print(f"\n=== {ch.id} ({ch.display_name}) ===")
        rec = {"id": ch.id, "display_name": ch.display_name,
               "identity_features": ch.identity_features, "tier": ch.tier, "seed": ch.seed,
               "style_denoise": args.style_denoise, "house_style_lora": None}
        try:
            process(ch, server=args.server, root=root, input_dir=input_dir, scratch=scratch,
                    style_denoise=args.style_denoise, record=rec)
            print(f"  done: {len(rec.get('stages', []))} stages, "
                  f"{len(rec.get('tokens', {}))} tokens")
        except SystemExit as e:
            # One character's failure must not cost the rest of the batch their GPU time.
            rec["failed"] = str(e)
            failures.append(ch.id)
            print(f"  FAILED: {e}")
        records[ch.id] = rec

    rec_path = root / "records.json"
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nrecords -> {rec_path}")
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
