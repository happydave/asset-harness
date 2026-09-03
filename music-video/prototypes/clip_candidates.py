#!/usr/bin/env python3
"""Clip stage: small-N Wan candidates for one video shot, objective gates only, owner pick (WI 1178).

  sweep MANIFEST --shot I --source-shot K --prompt "<motion>" [--n 2] [--seed-base 901] [--links 1]
        [--frames 33] [--width 1280] [--height 720] [--fps 16] [--run DIR] [--replace] [--make-video]
        Shot K's current asset is the source still (opaque RGB; K must not be adjacent to I -- the
        WI 1160 rule, refused before any GPU time). N candidates: --links 1 uses the production Wan
        recipe (all queued up front, each waited on); --links > 1 chains via chain_clip.build, which
        measures every seam. Gates are OBJECTIVE ONLY: integrity (frames, fps, size against the
        request) and, when chained, seam SSIM + acuity continuity. A failing candidate is culled with
        the gate named. Motion (ffmpeg scene scores; per link when chained) is recorded as a report,
        never gated. Survivors go on one sheet of first/middle/last-frame strips, shuffled and
        lettered, with the same pick_form.md the still stage uses.
  apply-form MANIFEST --run DIR
        cull_stills.apply_form -- owner letter + reason -> pick.
  provisional MANIFEST --shot I
        the FIRST surviving candidate, labelled machine-provisional: no video aesthetic signal exists
        (WI 1035 §4), so nothing here ranks clips.

Every write validates the manifest first, so a refused change leaves the file intact.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import chain_clip as cc
import comfy_client
import cull_stills as cs
import generate_clip as gc
import manifest as M

HERE = Path(__file__).resolve().parent
MAX_N = 4
GATE_FRAMES, GATE_FPS, GATE_SIZE, GATE_UNREADABLE = "integrity:frames", "integrity:fps", "integrity:size", "integrity:unreadable"
GATE_SSIM, GATE_ACUITY = "seam:ssim", "seam:acuity"
PROVISIONAL_REASON = "first surviving clip candidate; no video aesthetic signal exists (WI 1035 §4)"


class ClipError(ValueError):
    """A request that must be refused; the manifest on disk is left untouched."""


# --- pure core ----------------------------------------------------------------------------------

def fps_value(fps) -> float:
    """ffprobe's r_frame_rate is a string like '16/1'; compare numerically."""
    return float(Fraction(str(fps)))


def gate(probe: dict | None, *, frames: int, fps: int, width: int, height: int,
         seams: list[dict] | None = None) -> tuple[str, str, dict]:
    """(verdict, culled_by, integrity record). Objective gates only."""
    if probe is None:
        return "culled", GATE_UNREADABLE, {}
    rec = {"frames": probe["frames"], "fps": fps_value(probe["fps"]),
           "size": f"{probe['width']}x{probe['height']}", "expected_frames": frames}
    if probe["frames"] != frames:
        return "culled", GATE_FRAMES, rec
    if abs(fps_value(probe["fps"]) - fps) > 1e-6:
        return "culled", GATE_FPS, rec
    if (probe["width"], probe["height"]) != (width, height):
        return "culled", GATE_SIZE, rec
    for s in seams or []:
        if not s.get("ssim_pass", True):
            return "culled", GATE_SSIM, rec
    for s in seams or []:
        if not s.get("acuity_pass", True):
            return "culled", GATE_ACUITY, rec
    return "survivor", "", rec


def check_adjacent(shot: int, source_shot: int) -> None:
    if abs(shot - source_shot) == 1:
        raise ClipError(f"source shot {source_shot} is adjacent to shot {shot}: a motion clip must never "
                        f"sit next to its own source still (WI 1160) -- pick a source elsewhere")


# --- injectable side effects ---------------------------------------------------------------------

def motion_report(clip: Path) -> dict:
    """ffmpeg scene-change scores over the whole clip: mean/max frame-to-frame change."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(clip),
                        "-vf", "select='gt(scene,0)',metadata=print:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    sc = [float(l.split("=")[1]) for l in r.stdout.splitlines() if "scene_score" in l]
    return {"motion_scene_n": len(sc), "motion_scene_mean": round(sum(sc) / len(sc), 5) if sc else None,
            "motion_scene_max": round(max(sc), 5) if sc else None}


def probe_or_none(clip: Path) -> dict | None:
    try:
        return cc.probe(clip)
    except Exception:
        return None


def strip_sheet(clips: list[Path], letters: list[str], dst: Path) -> None:
    """One row per clip: first / middle / last frame, the letter drawn on the first tile."""
    inputs, filt = [], []
    for i, (clip, letter) in enumerate(zip(clips, letters)):
        inputs += ["-i", str(clip)]
        n = cc.probe(clip)["frames"]
        mid, last = n // 2, n - 1
        filt.append(f"[{i}:v]select='eq(n\\,0)+eq(n\\,{mid})+eq(n\\,{last})',scale=427:240,tile=3x1,"
                    f"drawtext=text='{letter}':x=12:y=10:fontsize=40:fontcolor=white:box=1:"
                    f"boxcolor=black@0.6:boxborderw=8[s{i}]")
    stack = "".join(f"[s{i}]" for i in range(len(clips)))
    filt.append(f"{stack}vstack=inputs={len(clips)}[out]" if len(clips) > 1 else "[s0]copy[out]")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *inputs, "-filter_complex",
                    ";".join(filt), "-map", "[out]", "-frames:v", "1", str(dst)], check=True)


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(Path(path).resolve(), base)


# --- sweep ----------------------------------------------------------------------------------------

def sweep(manifest_path: Path, *, shot: int, source_shot: int, prompt: str, n: int = 2, seed_base: int = 901,
          links: int = 1, frames: int = 33, width: int = 1280, height: int = 720, fps: int = 16,
          run_dir: Path, replace: bool = False, make_video: bool = False,
          server: str = comfy_client.DEFAULT_SERVER, client=comfy_client, chain_builder=cc.build,
          prober=probe_or_none, motion=motion_report, sheet=strip_sheet,
          opaque_check=cc.assert_opaque_rgb, run_id: str | None = None) -> dict:
    if not 1 <= n <= MAX_N:
        raise ClipError(f"--n must be 1..{MAX_N}: a clip costs ~2 min at 33 f (WI 1161); keep N small")
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    if not (0 <= shot < len(m.shots)) or not (0 <= source_shot < len(m.shots)):
        raise ClipError(f"shot indices must be within 0..{len(m.shots) - 1}")
    check_adjacent(shot, source_shot)
    s = m.shots[shot]
    if s.kind != "video":
        if not make_video:
            raise ClipError(f"shot {shot} is kind {s.kind!r}; pass --make-video to turn it into a clip shot")
        s.kind = "video"
    if s.candidates and not replace:
        raise ClipError(f"shot {shot} already has {len(s.candidates)} candidates; pass --replace to re-sweep")
    still = (mdir / m.shots[source_shot].asset).resolve()
    if not still.is_file():
        raise ClipError(f"source still missing on disk: {still}")
    opaque_check(still)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_dir.name
    seeds = [seed_base + j for j in range(n)]
    expected_frames = frames * links

    produced: dict[int, dict] = {}  # seed -> {path, seams}
    if links == 1:
        pending: dict[int, str] = {}
        uploaded = None
        for seed in seeds:
            stem = run_dir / f"shot{shot:02d}_seed{seed}"
            if stem.with_suffix(".mp4").exists():
                produced[seed] = {"path": stem.with_suffix(".mp4"), "seams": []}
                continue
            uploaded = uploaded or gc.upload_image(server, still) if client is comfy_client else f"{still.name}"
            graph = gc.build_graph(uploaded, prompt, width=width, height=height, frames=frames, fps=fps,
                                   seed=seed, use_lora=True, steps=4, cfg=1.0,
                                   prefix=f"asset_harness/mv_clipcand_{run_id}_{stem.name}")
            pending[seed] = client.queue(server, graph)
        print(f"sweep: {len(pending)} queued, {len(produced)} reused")
        for seed, pid in pending.items():
            stem = run_dir / f"shot{shot:02d}_seed{seed}"
            try:
                hist = client.wait_for_history(server, pid, label=stem.name)
                got = client.download_outputs(server, hist, stem, kinds=("videos", "gifs", "images"))[0]
                if got.suffix != ".mp4":
                    got = got.replace(stem.with_suffix(".mp4"))
                produced[seed] = {"path": got, "seams": []}
            except SystemExit as e:
                print(f"{stem.name}: FAILED ({e})")
    else:
        for seed in seeds:
            stem = run_dir / f"shot{shot:02d}_seed{seed}"
            try:
                rep = chain_builder(server, still, [prompt], links, stem, width=width, height=height,
                                    frames=frames, fps=fps, seed=seed, crossfade=0.0, denoise=True)
                (stem.with_suffix(".chain.json")).write_text(json.dumps(rep, indent=2) + "\n")
                produced[seed] = {"path": Path(rep["output"]), "seams": rep.get("seams", [])}
            except (SystemExit, cc.ChainError) as e:
                print(f"{stem.name}: FAILED ({e})")

    cands: list[M.Candidate] = []
    for seed in seeds:
        if seed not in produced:
            continue
        path, seams = produced[seed]["path"], produced[seed]["seams"]
        verdict, culled_by, integ = gate(prober(path), frames=expected_frames, fps=fps, width=width,
                                         height=height, seams=seams)
        scores = {**integ, "links": links}
        if seams:
            scores["seams"] = seams
        try:
            scores.update(motion(path))
            if links > 1:
                link_dir = path.parent / f"{path.stem}_links"
                per = [motion(p).get("motion_scene_mean") for p in sorted(link_dir.glob("link*.mp4"))]
                scores["motion_per_link"] = per
        except Exception as e:  # a report, never a gate: a failed probe must not cull
            scores["motion_error"] = str(e)[:120]
        cands.append(M.Candidate(
            asset=_rel(path, mdir),
            recipe={"high_unet": gc.HIGH_UNET, "low_unet": gc.LOW_UNET, "loras": [gc.HIGH_LORA, gc.LOW_LORA],
                    "seed": seed, "steps": 4, "cfg": 1.0, "shift": 5.0, "width": width, "height": height,
                    "frames": frames, "fps": fps, "links": links, "prompt": prompt},
            scores=scores, verdict=verdict, culled_by=culled_by,
            provenance={"source_shot": source_shot, "source_still": m.shots[source_shot].asset,
                        "prompt": prompt}))
    s.candidates = cands
    s.pick = None
    survivors = [c.asset for c in cands if c.verdict == "survivor"]
    summary = {"candidates": len(cands), "culled": [(c.asset, c.culled_by) for c in cands if c.verdict == "culled"],
               "survivors": len(survivors)}
    key: dict[str, dict[str, str]] = {}
    if survivors:
        order = cs.shuffled(survivors, run_id, shot)
        letters = list(cs.LETTERS[:len(order)])
        sheet_path = run_dir / f"shot{shot:02d}_sheet.png"
        sheet([(mdir / a).resolve() for a in order], letters, sheet_path)
        key[f"shot {shot:02d}"] = dict(zip(letters, order))
        summary["sheet"] = sheet_path.name
        form_shots = [(shot, sheet_path.name, letters)]
    else:
        form_shots = []
    text = M.to_json(m, manifest_dir=mdir)  # validate before touching anything
    manifest_path.write_text(text)
    (run_dir / "_tile_key.json").write_text(json.dumps({"run_id": run_id, "manifest": str(manifest_path),
                                                        "shots": key}, indent=2) + "\n")
    (run_dir / "pick_form.md").write_text(cs.form_text(form_shots))
    summary["form"] = str(run_dir / "pick_form.md")
    return summary


def provisional(manifest_path: Path, shot: int) -> dict:
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    s = m.shots[shot]
    if s.pick is not None:
        return {"skipped": f"shot {shot} already has a {s.pick.picked_by} pick"}
    first = next((c for c in s.candidates if c.verdict == "survivor"), None)
    if first is None:
        raise ClipError(f"shot {shot}: no surviving clip candidate -- re-sweep with new seeds")
    for c in s.candidates:
        if c.verdict == "survivor":
            c.verdict = "passed-over"
    first.verdict = "chosen"
    s.asset = first.asset
    s.pick = M.Pick(picked_by="machine-provisional", reason=PROVISIONAL_REASON)
    manifest_path.write_text(M.to_json(m, manifest_dir=mdir))
    return {"picked": first.asset}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sweep")
    p.add_argument("manifest"); p.add_argument("--shot", type=int, required=True)
    p.add_argument("--source-shot", type=int, required=True); p.add_argument("--prompt", required=True)
    p.add_argument("--n", type=int, default=2); p.add_argument("--seed-base", type=int, default=901)
    p.add_argument("--links", type=int, default=1); p.add_argument("--frames", type=int, default=33)
    p.add_argument("--width", type=int, default=1280); p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=16); p.add_argument("--run", default=None)
    p.add_argument("--replace", action="store_true"); p.add_argument("--make-video", action="store_true")
    p.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    a = sub.add_parser("apply-form"); a.add_argument("manifest"); a.add_argument("--run", required=True)
    v = sub.add_parser("provisional"); v.add_argument("manifest"); v.add_argument("--shot", type=int, required=True)
    args = ap.parse_args(argv)
    mp = Path(args.manifest).resolve()
    try:
        if args.cmd == "sweep":
            run_dir = Path(args.run) if args.run else mp.parent / f"clips-shot{args.shot:02d}"
            summ = sweep(mp, shot=args.shot, source_shot=args.source_shot, prompt=args.prompt, n=args.n,
                         seed_base=args.seed_base, links=args.links, frames=args.frames, width=args.width,
                         height=args.height, fps=args.fps, run_dir=run_dir, replace=args.replace,
                         make_video=args.make_video, server=args.server)
            print(f"{summ['candidates']} candidates, {summ['survivors']} survivors")
            for asset, why in summ["culled"]:
                print(f"  culled {asset} [{why}]")
            if summ["survivors"]:
                print(f"-> fill {summ['form']} then: python3 clip_candidates.py apply-form {mp} --run {run_dir}")
            else:
                print("-> no survivors: re-sweep with new seeds")
                return 2
            print("reminder: restart ComfyUI before an ACE-Step / Z-Image batch (ssh ai2 systemctl restart comfyui.service)")
        elif args.cmd == "apply-form":
            r = cs.apply_form(mp, Path(args.run))
            for idx, letter, asset in r["applied"]:
                print(f"  shot {idx:02d}: {letter} -> {asset}")
            if r["blank"]:
                print(f"  unanswered: shots {r['blank']}")
        else:
            r = provisional(mp, args.shot)
            print(f"  shot {args.shot:02d}: {r}")
    except (ClipError, cs.CullError, cc.ChainError, M.ManifestError, FileNotFoundError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
