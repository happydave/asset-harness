#!/usr/bin/env python3
"""Song stage: sweep seeds -> save-time QC gate -> Audiobox CE rank -> auto-pick -> record (WI 1176).

Productizes what the production sessions did by hand. For a song spec (the `generate_song.SONG`
shape as JSON: name, seconds, bpm, key, tags, lyrics):

  1. sweep     one ACE-Step graph per seed, all queued up front, then each waited on and downloaded
               (the WI 1020 rule: wait on the server's job state, never a wall clock). A candidate
               already on disk is reused, so a run resumes.
  2. QC gate   generate_song's save-time postprocess: the -1 dBTP ceiling (a transform, never a
               signal) plus the WI 1046 truncation check. Truncated => culled by "qc:truncation".
  3. score     Audiobox Aesthetics (CE/CU/PC/PQ) in the scoring venv as a subprocess
               (scoring/score_audiobox.py), with its determinism control.
  4. pick      the top-CE candidate among the unvetoed is `chosen` (picked_by machine-auto); the
               rest are `passed-over`. A vetoed candidate is never promoted whatever its CE.
               No CE score, or a failed determinism control => candidates recorded, NO pick, exit 1:
               the owner picks with `repick.py pick --song`.
  5. record    <name>.song.json beside the flacs, built from manifest.Candidate / manifest.Pick so
               the shapes cannot drift; `--into MANIFEST` lands the block in an existing manifest
               (audio + song_candidates + song_pick + scorer_versions), validated before writing.

    python3 select_song.py --spec inputs/clamor_hold_the_line.song.json --seeds 701,702,703
    python3 select_song.py --spec ... --into outputs/lobby/clamor_lobby.manifest.json

Exit codes: 0 picked; 1 recorded without a pick (or a refused --into); 2 no candidate survived.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import comfy_client
import generate_song as gs
import manifest as M

HERE = Path(__file__).resolve().parent
SCORING = HERE / "scoring"
SCORER_VERSIONS_STATIC = {"audio_qc": "wi1046"}
TRUNCATION_GATE = "qc:truncation"


def spec_hashes(spec: dict) -> dict:
    """What a song candidate was generated FROM -- the staleness audit's comparison keys."""
    core = json.dumps({k: spec[k] for k in ("tags", "lyrics", "bpm", "key", "seconds")}, sort_keys=True)
    return {"spec_sha256": hashlib.sha256(core.encode()).hexdigest(),
            "lyrics_sha256": hashlib.sha256(spec["lyrics"].encode()).hexdigest()}


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text())
    missing = [k for k in ("name", "seconds", "bpm", "key", "tags", "lyrics") if k not in spec]
    if missing:
        raise SystemExit(f"song spec {path} is missing {missing}")
    return spec


# --- the injectable steps (tests replace these) -------------------------------------------------

def generate_sweep(server: str, spec: dict, seeds: list[int], out_dir: Path, *,
                   checkpoint: str, ceiling: float | None) -> dict[int, dict]:
    """seed -> {path, qc} for every seed that produced a file; seeds already on disk are reused."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, dict] = {}
    pending: dict[int, str] = {}
    for seed in seeds:
        stem = out_dir / f"{spec['name']}_seed{seed}"
        existing = next((p for p in out_dir.glob(stem.name + ".*") if p.suffix in (".flac", ".wav", ".mp3")), None)
        if existing:
            print(f"seed {seed}: reusing {existing.name}")
            results[seed] = {"path": existing, "qc": _qc_only(existing)}
            continue
        graph = gs.build_graph(spec, seed, f"asset_harness/mv_{stem.name}", checkpoint=checkpoint)
        pending[seed] = comfy_client.queue(server, graph)
        print(f"seed {seed}: queued {pending[seed]}")
    for seed, pid in pending.items():
        stem = out_dir / f"{spec['name']}_seed{seed}"
        try:
            hist = comfy_client.wait_for_history(server, pid, label=f"seed{seed}")
            path = comfy_client.download_outputs(server, hist, stem, kinds=("audio",))[0]
        except SystemExit as e:
            print(f"seed {seed}: FAILED ({e})")
            continue
        results[seed] = {"path": path, "qc": gs._postprocess(path, ceiling=ceiling)}
        print(f"seed {seed}: {path.name}  truncated={results[seed]['qc'].get('truncated')}")
    return results


def _qc_only(path: Path) -> dict:
    """QC without re-applying the ceiling (a reused file was ceilinged when it was made)."""
    return gs._postprocess(path, ceiling=None)


def score_audiobox(paths: list[Path]) -> dict:
    """Run scoring/score_audiobox.py in the scoring venv. Returns its JSON, or {"error": ...}."""
    venv_py = SCORING / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return {"error": f"scoring venv not found at {venv_py}; create it: cd {SCORING} && "
                         "python3 -m venv .venv && .venv/bin/pip install <packages named in scoring/*.py headers>"}
    cmd = [str(venv_py), str(SCORING / "score_audiobox.py"), *map(str, paths)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600)
        return json.loads(r.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"error": f"score_audiobox failed: {str(getattr(e, 'stderr', e))[-400:]}"}


# --- the pure core ------------------------------------------------------------------------------

def build_record(spec: dict, sweep: dict[int, dict], scores: dict, *, out_dir: Path,
                 checkpoint: str) -> dict:
    """Candidates + pick from the sweep and the scorer output. Pure: no I/O, fully testable."""
    ck = gs.CHECKPOINTS[checkpoint]
    prov = {**spec_hashes(spec), "checkpoint": checkpoint}
    by_stem = scores.get("scores", {})
    deterministic = scores.get("controls", {}).get("audiobox_deterministic")
    cands: list[M.Candidate] = []
    for seed in sorted(sweep):
        path, qc = sweep[seed]["path"], sweep[seed]["qc"]
        stem = Path(path).stem
        sc = {"true_peak_dbtp": qc.get("true_peak_dbtp"), "end_decay_s": qc.get("end_decay_s"),
              "truncated": bool(qc.get("truncated"))}
        for axis, val in by_stem.get(stem, {}).items():
            sc[f"audiobox_{axis}"] = val
        truncated = bool(qc.get("truncated"))
        cands.append(M.Candidate(
            asset=str(Path(path).relative_to(out_dir)) if Path(path).is_relative_to(out_dir) else str(path),
            recipe={"unet": ck["unet"], "checkpoint": checkpoint, "seed": seed, "steps": ck["steps"],
                    "cfg": ck["cfg"], "tags": spec["tags"], "bpm": spec["bpm"], "key": spec["key"],
                    "seconds": spec["seconds"]},
            scores=sc,
            verdict="culled" if truncated else "survivor",
            culled_by=TRUNCATION_GATE if truncated else "",
            provenance=prov))

    unvetoed = [c for c in cands if c.verdict != "culled"]
    scored = [c for c in unvetoed if "audiobox_CE" in c.scores]
    pick = None
    reason_no_pick = None
    if not cands:
        reason_no_pick = "no candidate was generated"
    elif not unvetoed:
        reason_no_pick = f"all {len(cands)} candidates truncated -- re-roll seeds or shorten the lyrics/duration"
    elif "error" in scores:
        reason_no_pick = scores["error"]
    elif deterministic is False:
        reason_no_pick = "audiobox determinism control FAILED -- its ranking is not trusted for this run"
    elif not scored:
        reason_no_pick = "no unvetoed candidate has an audiobox CE score"
    else:
        best = max(scored, key=lambda c: c.scores["audiobox_CE"])
        for c in unvetoed:
            c.verdict = "passed-over"
        best.verdict = "chosen"
        pick = M.Pick(picked_by="machine-auto",
                      reason=f"top Audiobox CE {best.scores['audiobox_CE']} among {len(scored)} unvetoed of {len(cands)}")
    versions = dict(SCORER_VERSIONS_STATIC)
    if scores.get("version"):
        versions["audiobox_aesthetics"] = scores["version"]
    chosen = next((c for c in cands if c.verdict == "chosen"), None)
    return {"spec": spec, "audio": chosen.asset if chosen else None,
            "candidates": [asdict(c) for c in cands],
            "pick": asdict(pick) if pick else None,
            "no_pick_reason": reason_no_pick,
            "scorer_versions": versions,
            "controls": scores.get("controls", {})}


def record_exit_code(rec: dict) -> int:
    if rec["pick"]:
        return 0
    return 2 if not any(c["verdict"] != "culled" for c in rec["candidates"]) or not rec["candidates"] else 1


def apply_into(rec: dict, manifest_path: Path, record_dir: Path) -> None:
    """Land the song block in an existing manifest. Validates before writing; raises on refusal."""
    m = M.from_json(manifest_path.read_text())
    mdir = manifest_path.resolve().parent
    cands = []
    for c in rec["candidates"]:
        c2 = dict(c)
        c2["asset"] = _rel(record_dir / c["asset"], mdir)
        cands.append(M.Candidate(**c2))
    m.song_candidates = cands
    m.song_pick = M.Pick(**rec["pick"]) if rec["pick"] else None
    if rec["audio"]:
        m.audio = _rel(record_dir / rec["audio"], mdir)
    m.scorer_versions = {**m.scorer_versions, **rec["scorer_versions"]}
    text = M.to_json(m, manifest_dir=mdir)  # validate BEFORE touching the file
    manifest_path.write_text(text)


def _rel(path: Path, base: Path) -> str:
    import os
    return os.path.relpath(path.resolve(), base)


def print_summary(rec: dict) -> None:
    for c in rec["candidates"]:
        ce = c["scores"].get("audiobox_CE")
        print(f"  {c['verdict']:<11} {c['asset']:<40} CE={ce if ce is not None else '-':<8} "
              f"peak={c['scores'].get('true_peak_dbtp')} dBTP"
              + (f"  [{c['culled_by']}]" if c["culled_by"] else ""))
    if rec["pick"]:
        print(f"-> picked {rec['audio']} ({rec['pick']['picked_by']}: {rec['pick']['reason']})")
    else:
        print(f"-> NO PICK: {rec['no_pick_reason']}")
        if rec["candidates"]:
            print("   pick by hand: python3 repick.py pick <manifest> --song --to <asset> --by owner --reason '...'")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True, help="song spec JSON (name, seconds, bpm, key, tags, lyrics)")
    ap.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    ap.add_argument("--seeds", default="701,702,703", help="comma-separated; the design's default N is 3")
    ap.add_argument("--checkpoint", default=gs.DEFAULT_CHECKPOINT, choices=sorted(gs.CHECKPOINTS))
    ap.add_argument("--no-ceiling", action="store_true")
    ap.add_argument("--out", default=None, help="candidate dir (default outputs/<name>/song)")
    ap.add_argument("--into", default=None, help="existing manifest to land the song block in")
    args = ap.parse_args(argv)

    spec = load_spec(Path(args.spec))
    seeds = list(dict.fromkeys(int(s) for s in args.seeds.split(",") if s.strip()))
    out_dir = Path(args.out) if args.out else HERE / "outputs" / spec["name"] / "song"
    ceiling = None if args.no_ceiling else gs.CEILING_DBTP

    sweep = generate_sweep(args.server, spec, seeds, out_dir, checkpoint=args.checkpoint, ceiling=ceiling)
    scores = score_audiobox([Path(v["path"]) for _, v in sorted(sweep.items())]) if sweep else {"error": "nothing to score"}
    rec = build_record(spec, sweep, scores, out_dir=out_dir, checkpoint=args.checkpoint)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_path = out_dir / f"{spec['name']}.song.json"
    rec_path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"record -> {rec_path}")
    print_summary(rec)
    code = record_exit_code(rec)
    if args.into:
        try:
            apply_into(rec, Path(args.into), out_dir)
            print(f"-> song block written into {args.into}")
        except (M.ManifestError, OSError, KeyError) as e:
            print(f"refused --into {args.into}: {e}", file=sys.stderr)
            return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
