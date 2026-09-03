#!/usr/bin/env python3
"""Still stage: seed sweep -> group-relative cull -> shuffled lettered contact sheets + one form ->
owner pick recorded (WI 1177). Three subcommands over a manifest:

  sweep MANIFEST [--shots 0,3] [--n 5] [--seed-base 41] [--run DIR] [--replace]
        For each still/kenburns shot: N Z-Image candidates (all queued up front, each waited on;
        files already in DIR are reused), scored whole-frame (letterbox CLIP-vs-prompt + PickScore)
        in the scoring venv, culled ONLY when far below their own group (see CULL_*), and recorded
        in the shot's candidate list with scores, verdict, gate and provenance. Survivors go on one
        contact sheet per shot -- tile order SHUFFLED by a recorded seed (presentation order is a
        measured confound, WI 1179) -- with DIR/pick_form.md and DIR/_tile_key.json.
        The shot's current `asset` is left alone until a pick.
  apply-form MANIFEST --run DIR
        Read the filled form: `Pick: <letter>` + `Why: <reason>` per shot -> that candidate
        `chosen`, the other survivors `passed-over`, `asset` updated, pick recorded as `owner`
        with the reason. Blank shots are left untouched and listed. A bad letter refuses the whole
        apply; nothing is written.
  provisional MANIFEST
        For every shot with survivors and no pick: the top-PickScore survivor becomes `chosen`,
        labelled `machine-provisional` -- a draft the owner re-picks later (repick.py), never an
        owner pick.

The cull rule is calibrated on the archived WI 1037 + WI 1111 corpora (test_cull_stills.py replays
them): the lowest real candidate sits at 0.909x its group's median CLIP and 0.938x on PickScore; the
off-brief control at 0.305x / 0.670x. Culling needs BOTH scorers far below (clip < 0.60x AND
pickscore < 0.85x) or CLIP alone catastrophic (< 0.45x), and a group of at least 3 to be relative to.

Every write validates the manifest first (manifest.to_json), so a refused change leaves the file intact.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import string
import subprocess
import sys
import tempfile
from pathlib import Path

import comfy_client
import generate_still as gi
import manifest as M

HERE = Path(__file__).resolve().parent
SCORING = HERE / "scoring"
CULL_CLIP_BOTH = 0.60
CULL_PICK_BOTH = 0.85
CULL_CLIP_ALONE = 0.45
MIN_GROUP = 3
MAX_N = 26  # sheets are lettered
GATE_BOTH = "cull:clip+pickscore"
GATE_CLIP = "cull:clip"
LETTERS = string.ascii_uppercase


class CullError(ValueError):
    """A request that must be refused; the manifest on disk is left untouched."""


# --- pure core ----------------------------------------------------------------------------------

def cull(scores: dict[str, dict]) -> dict[str, dict]:
    """asset -> {verdict, culled_by, clip_ratio, pickscore_ratio}. Group-relative; conservative."""
    valid = {k: v for k, v in scores.items()
             if v.get("clip_letterbox") is not None and v.get("pickscore_letterbox") is not None}
    out = {k: {"verdict": "survivor", "culled_by": "", "clip_ratio": None, "pickscore_ratio": None}
           for k in scores}
    if len(valid) < MIN_GROUP:
        return out
    med_c = statistics.median(v["clip_letterbox"] for v in valid.values())
    med_p = statistics.median(v["pickscore_letterbox"] for v in valid.values())
    for k, v in valid.items():
        rc = v["clip_letterbox"] / med_c if med_c else 1.0
        rp = v["pickscore_letterbox"] / med_p if med_p else 1.0
        out[k]["clip_ratio"], out[k]["pickscore_ratio"] = round(rc, 4), round(rp, 4)
        if rc < CULL_CLIP_BOTH and rp < CULL_PICK_BOTH:
            out[k].update(verdict="culled", culled_by=GATE_BOTH)
        elif rc < CULL_CLIP_ALONE:
            out[k].update(verdict="culled", culled_by=GATE_CLIP)
    return out


def shuffled(assets: list[str], run_id: str, shot_index: int) -> list[str]:
    """A deterministic, recorded shuffle: the same run id and shot give the same order."""
    order = list(assets)
    random.Random(f"{run_id}:{shot_index}").shuffle(order)
    return order


def form_text(shots: list[tuple[int, str, list[str]]]) -> str:
    """shots: (index, sheet filename, letters). One folder, one file, one answer per shot."""
    lines = ["# Still picks\n",
             "\nEverything is in THIS folder. For each shot open its sheet, choose one tile, and write\n"
             "the letter after `Pick:` and a few words after `Why:` (what made it win -- composition,\n"
             "light, on-brief-ness). The reason matters: it is recorded with the pick. Tiles are in a\n"
             "shuffled order on purpose; the mapping is in `_tile_key.json` -- no need to open it.\n"]
    for idx, sheet, letters in shots:
        lines.append(f"\n## shot {idx:02d} — open `{sheet}` (tiles {letters[0]}–{letters[-1]})\n"
                     f"- Pick: \n- Why: \n")
    return "".join(lines)


def parse_form(text: str) -> dict[int, dict]:
    """{shot index: {"pick": letter or "", "why": text}} for every shot section in the form."""
    out: dict[int, dict] = {}
    cur = None
    for raw in text.splitlines():
        m = re.match(r"^## shot (\d+)", raw)
        if m:
            cur = int(m.group(1))
            out[cur] = {"pick": "", "why": ""}
            continue
        if cur is None:
            continue
        m = re.match(r"^- Pick:\s*(.*)$", raw)
        if m:
            out[cur]["pick"] = m.group(1).strip().strip("`*").upper()[:1]
            continue
        m = re.match(r"^- Why:\s*(.*)$", raw)
        if m:
            out[cur]["why"] = m.group(1).strip()
    return out


# --- injectable steps -----------------------------------------------------------------------------

def score_stills(items: list[dict]) -> dict:
    """Run scoring/score_stills.py in the scoring venv. items: [{path, prompt}]."""
    venv_py = SCORING / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return {"error": f"scoring venv not found at {venv_py}"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(items, fh)
        spec = fh.name
    try:
        r = subprocess.run([str(venv_py), str(SCORING / "score_stills.py"), spec],
                           capture_output=True, text=True, check=True, timeout=3600)
        return json.loads(r.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"error": f"score_stills failed: {str(getattr(e, 'stderr', e))[-400:]}"}
    finally:
        os.unlink(spec)


def tile_sheet(images: list[Path], dst: Path) -> None:
    sys.path.insert(0, str(SCORING))
    import build_ranking
    build_ranking.tile(images, dst, cols=len(images))


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(Path(path).resolve(), base)


# --- sweep ----------------------------------------------------------------------------------------

def sweep(manifest_path: Path, *, shots: list[int] | None, n: int, seed_base: int, model: str,
          run_dir: Path, replace: bool = False, server: str = comfy_client.DEFAULT_SERVER,
          client=comfy_client, scorer=score_stills, tiler=tile_sheet, run_id: str | None = None) -> dict:
    if not 1 <= n <= MAX_N:
        raise CullError(f"--n must be 1..{MAX_N} (sheets are lettered)")
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_dir.name
    targets = [s for s in m.shots if s.kind != "video" and (shots is None or s.index in shots)]
    refused = [s.index for s in targets if s.candidates and not replace]
    if refused:
        raise CullError(f"shots {refused} already have candidates; pass --replace to re-sweep them")
    preset = gi.MODELS[model]
    seeds = [seed_base + i for i in range(n)]

    # 1. sweep: queue everything, then wait in order (WI 1020 rule)
    files: dict[tuple[int, int], Path] = {}
    pending: dict[tuple[int, int], str] = {}
    for s in targets:
        for seed in seeds:
            stem = run_dir / f"shot{s.index:02d}_seed{seed}"
            if stem.with_suffix(".png").exists():
                files[(s.index, seed)] = stem.with_suffix(".png")
                continue
            graph = gi.build_graph(s.prompt, gi.DEFAULT_NEGATIVE, width=1280, height=720, seed=seed,
                                   model=model, steps=preset["steps"], cfg=preset["cfg"],
                                   prefix=f"asset_harness/mv_cull_{run_id}_{stem.name}")
            pending[(s.index, seed)] = client.queue(server, graph)
    print(f"sweep: {len(pending)} queued, {len(files)} reused")
    for key, pid in pending.items():
        stem = run_dir / f"shot{key[0]:02d}_seed{key[1]}"
        try:
            hist = client.wait_for_history(server, pid, label=stem.name)
            files[key] = client.download_outputs(server, hist, stem, kinds=("images",))[0]
        except SystemExit as e:
            print(f"{stem.name}: FAILED ({e})")

    # 2. score all at once (one model load)
    by_shot = {s.index: s for s in targets}
    items = [{"path": str(p), "prompt": by_shot[k[0]].prompt} for k, p in sorted(files.items())]
    scored = scorer(items) if items else {"error": "nothing to score"}
    if "error" in scored:
        print(f"scoring unavailable: {scored['error']} -- recording candidates without scores")
    sc = scored.get("scores", {})
    versions = scored.get("versions", {})

    # 3. cull + record + sheets
    summary = {"shots": {}, "culled": 0, "candidates": 0, "no_survivors": [],
               "controls": scored.get("controls", {})}
    key_file: dict[str, dict[str, str]] = {}
    form_shots: list[tuple[int, str, list[str]]] = []
    for s in targets:
        group = {str(p): sc.get(str(p), {}) for k, p in sorted(files.items()) if k[0] == s.index}
        verdicts = cull(group)
        cands: list[M.Candidate] = []
        for k, p in sorted(files.items()):
            if k[0] != s.index:
                continue
            v = verdicts[str(p)]
            scores = dict(sc.get(str(p), {}))
            scores.update({"clip_ratio": v["clip_ratio"], "pickscore_ratio": v["pickscore_ratio"]})
            cands.append(M.Candidate(
                asset=_rel(p, mdir),
                recipe={"model": model, "unet": preset["unet"], "seed": k[1], "steps": preset["steps"],
                        "cfg": preset["cfg"], "width": 1280, "height": 720, "negative": gi.DEFAULT_NEGATIVE},
                scores=scores, verdict=v["verdict"], culled_by=v["culled_by"],
                provenance={"prompt": s.prompt, "lines": s.lines}))
        s.candidates = cands
        s.pick = None
        summary["candidates"] += len(cands)
        summary["culled"] += sum(1 for c in cands if c.verdict == "culled")
        survivors = [c.asset for c in cands if c.verdict == "survivor"]
        if not survivors:
            summary["no_survivors"].append(s.index)
            summary["shots"][s.index] = {"survivors": 0}
            continue
        order = shuffled(survivors, run_id, s.index)
        letters = LETTERS[:len(order)]
        sheet = run_dir / f"shot{s.index:02d}_sheet.png"
        tiler([(mdir / a).resolve() for a in order], sheet)
        key_file[f"shot {s.index:02d}"] = dict(zip(letters, order))
        form_shots.append((s.index, sheet.name, list(letters)))
        summary["shots"][s.index] = {"survivors": len(order), "sheet": sheet.name}
    m.scorer_versions = {**m.scorer_versions, **{f"still_{k}": v for k, v in versions.items()}}
    text = M.to_json(m, manifest_dir=mdir)  # validate before touching anything
    manifest_path.write_text(text)
    (run_dir / "_tile_key.json").write_text(json.dumps({"run_id": run_id, "manifest": str(manifest_path),
                                                        "shots": key_file}, indent=2) + "\n")
    (run_dir / "pick_form.md").write_text(form_text(form_shots))
    summary["form"] = str(run_dir / "pick_form.md")
    return summary


# --- apply-form -----------------------------------------------------------------------------------

def apply_form(manifest_path: Path, run_dir: Path, *, date: str | None = None) -> dict:
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    key = json.loads((run_dir / "_tile_key.json").read_text())["shots"]
    answers = parse_form((run_dir / "pick_form.md").read_text())
    applied, blank = [], []
    for idx, ans in sorted(answers.items()):
        if not ans["pick"]:
            blank.append(idx)
            continue
        mapping = key.get(f"shot {idx:02d}", {})
        if ans["pick"] not in mapping:
            raise CullError(f"shot {idx:02d}: pick {ans['pick']!r} is not a tile letter "
                            f"({', '.join(mapping) or 'no sheet'}); nothing written")
        asset = mapping[ans["pick"]]
        shot = next((s for s in m.shots if s.index == idx), None)
        if shot is None:
            raise CullError(f"shot {idx:02d} is not in the manifest; nothing written")
        target = next((c for c in shot.candidates if c.asset == asset), None)
        if target is None:
            raise CullError(f"shot {idx:02d}: {asset} is not a recorded candidate; nothing written")
        for c in shot.candidates:
            if c.verdict in ("chosen", "survivor", "passed-over"):
                c.verdict = "passed-over"
        target.verdict = "chosen"
        history = list(shot.pick.history) if shot.pick else []
        if shot.pick is not None:
            history.append({"asset": shot.asset, "picked_by": shot.pick.picked_by,
                            "reason": shot.pick.reason, "date": date or _today()})
        shot.asset = asset
        shot.pick = M.Pick(picked_by="owner", reason=ans["why"], history=history)
        applied.append((idx, ans["pick"], asset))
    text = M.to_json(m, manifest_dir=mdir)
    manifest_path.write_text(text)
    return {"applied": applied, "blank": blank}


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# --- provisional ----------------------------------------------------------------------------------

def provisional(manifest_path: Path) -> dict:
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    picked, skipped = [], []
    for s in m.shots:
        if not s.candidates or s.pick is not None:
            continue
        surv = [c for c in s.candidates if c.verdict == "survivor"
                and c.scores.get("pickscore_letterbox") is not None]
        if not surv:
            skipped.append((s.index, "no scored survivor to rank by"))
            continue
        best = max(surv, key=lambda c: c.scores["pickscore_letterbox"])
        for c in s.candidates:
            if c.verdict == "survivor":
                c.verdict = "passed-over"
        best.verdict = "chosen"
        s.asset = best.asset
        s.pick = M.Pick(picked_by="machine-provisional",
                        reason=f"top PickScore survivor {best.scores['pickscore_letterbox']} (provisional draft)")
        picked.append((s.index, best.asset))
    text = M.to_json(m, manifest_dir=mdir)
    manifest_path.write_text(text)
    return {"picked": picked, "skipped": skipped}


# --- CLI ------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sweep")
    p.add_argument("manifest")
    p.add_argument("--shots", default=None, help="comma-separated shot indices (default: every still shot)")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed-base", type=int, default=41)
    p.add_argument("--model", default="base", choices=sorted(gi.MODELS))
    p.add_argument("--run", default=None, help="run folder (default: <manifest dir>/stills-<n>x)")
    p.add_argument("--replace", action="store_true", help="re-sweep shots that already have candidates")
    p.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    a = sub.add_parser("apply-form")
    a.add_argument("manifest")
    a.add_argument("--run", required=True)
    v = sub.add_parser("provisional")
    v.add_argument("manifest")
    args = ap.parse_args(argv)
    mp = Path(args.manifest).resolve()
    try:
        if args.cmd == "sweep":
            run_dir = Path(args.run) if args.run else mp.parent / f"stills-{args.n}x"
            shots = [int(x) for x in args.shots.split(",")] if args.shots else None
            summ = sweep(mp, shots=shots, n=args.n, seed_base=args.seed_base, model=args.model,
                         run_dir=run_dir, replace=args.replace, server=args.server)
            for idx, info in sorted(summ["shots"].items()):
                print(f"  shot {idx:02d}: {info['survivors']} survivors" + (f" -> {info['sheet']}" if info.get("sheet") else ""))
            print(f"{summ['candidates']} candidates, {summ['culled']} culled; controls {summ['controls']}")
            if summ["no_survivors"]:
                print(f"  no survivors for shots {summ['no_survivors']}: re-sweep with new seeds")
            print(f"-> fill {summ['form']} then: python3 cull_stills.py apply-form {mp} --run {run_dir}")
        elif args.cmd == "apply-form":
            r = apply_form(mp, Path(args.run))
            for idx, letter, asset in r["applied"]:
                print(f"  shot {idx:02d}: {letter} -> {asset}")
            if r["blank"]:
                print(f"  unanswered: shots {r['blank']}")
        else:
            r = provisional(mp)
            for idx, asset in r["picked"]:
                print(f"  shot {idx:02d}: provisional -> {asset}")
            for idx, why in r["skipped"]:
                print(f"  shot {idx:02d}: skipped ({why})")
    except (CullError, M.ManifestError, FileNotFoundError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
