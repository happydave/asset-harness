#!/usr/bin/env python3
"""Checks for select_song.py. Plain `python3 test_select_song.py`; no server, no venv, no GPU.

The sweep and the scorer are injected fakes; build_record is pure, so the veto rule, the ranking and
the record shape are exercised deterministically. One check lands a record into a fixture manifest
through apply_into and validates it with manifest.py.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as M
import select_song as ss

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + str(detail)}")
    if not cond:
        FAILURES.append(label)


SPEC = json.loads((Path(__file__).with_name("inputs") / "clamor_hold_the_line.song.json").read_text())


def sweep(tmp: Path, seeds, truncated=()):
    out = {}
    for s in seeds:
        p = tmp / f"{SPEC['name']}_seed{s}.flac"
        p.write_bytes(b"fLaC")
        out[s] = {"path": p, "qc": {"truncated": s in truncated, "end_decay_s": 1.0,
                                    "true_peak_dbtp": -1.0}}
    return out


def scores(tmp, ce: dict, deterministic=True, version="0.0.4"):
    return {"scores": {f"{SPEC['name']}_seed{s}": {"CE": v, "CU": 5.0, "PC": 5.0, "PQ": 5.0}
                       for s, v in ce.items()},
            "controls": {"audiobox_deterministic": deterministic}, "version": version}


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    # helpers
    h1, h2 = ss.spec_hashes(SPEC), ss.spec_hashes({**SPEC, "lyrics": SPEC["lyrics"] + "\nextra"})
    check("spec hash changes with lyrics", h1["spec_sha256"] != h2["spec_sha256"] and h1["lyrics_sha256"] != h2["lyrics_sha256"])
    check("spec hash ignores name", ss.spec_hashes({**SPEC, "name": "other"}) == h1)

    # happy path
    sw = sweep(tmp, [701, 702, 703])
    rec = ss.build_record(SPEC, sw, scores(tmp, {701: 7.1, 702: 7.9, 703: 7.4}), out_dir=tmp, checkpoint="turbo")
    verd = {c["recipe"]["seed"]: c["verdict"] for c in rec["candidates"]}
    check("happy: top CE chosen", verd == {701: "passed-over", 702: "chosen", 703: "passed-over"}, verd)
    check("happy: audio is the chosen asset", rec["audio"] == f"{SPEC['name']}_seed702.flac", rec["audio"])
    check("happy: pick is machine-auto with reason", rec["pick"]["picked_by"] == "machine-auto" and "7.9" in rec["pick"]["reason"])
    check("happy: exit 0", ss.record_exit_code(rec) == 0)
    c0 = rec["candidates"][0]
    check("record: recipe carries seed/unet/steps/cfg", c0["recipe"]["seed"] == 701 and c0["recipe"]["unet"].endswith("turbo_bf16.safetensors")
          and c0["recipe"]["steps"] == 8 and c0["recipe"]["cfg"] == 1.0, c0["recipe"])
    check("record: scores carry audiobox axes + qc", {"audiobox_CE", "audiobox_CU", "audiobox_PC", "audiobox_PQ", "true_peak_dbtp", "truncated"} <= set(c0["scores"]))
    check("record: provenance carries spec hash + checkpoint", c0["provenance"]["checkpoint"] == "turbo" and len(c0["provenance"]["spec_sha256"]) == 64)
    check("record: scorer versions", rec["scorer_versions"] == {"audio_qc": "wi1046", "audiobox_aesthetics": "0.0.4"}, rec["scorer_versions"])
    check("record: candidates round-trip the substrate dataclasses",
          all(M.Candidate(**c).verdict in M.VERDICTS for c in rec["candidates"]) and M.Pick(**rec["pick"]).picked_by in M.PICKERS)

    # veto rule: the best CE is truncated
    sw = sweep(tmp, [701, 702, 703], truncated=(702,))
    rec = ss.build_record(SPEC, sw, scores(tmp, {701: 7.1, 702: 9.9, 703: 7.4}), out_dir=tmp, checkpoint="turbo")
    verd = {c["recipe"]["seed"]: (c["verdict"], c["culled_by"]) for c in rec["candidates"]}
    check("veto: truncated top-CE is culled by qc:truncation, not promoted",
          verd[702] == ("culled", "qc:truncation") and verd[703] == ("chosen", ""), verd)
    check("veto: exit 0 (a pick exists)", ss.record_exit_code(rec) == 0)

    # all truncated
    rec = ss.build_record(SPEC, sweep(tmp, [701, 702], truncated=(701, 702)), scores(tmp, {701: 8, 702: 9}), out_dir=tmp, checkpoint="turbo")
    check("all truncated: no pick, exit 2, message says re-roll", rec["pick"] is None and ss.record_exit_code(rec) == 2 and "re-roll" in rec["no_pick_reason"])

    # no candidates
    rec = ss.build_record(SPEC, {}, {"error": "nothing to score"}, out_dir=tmp, checkpoint="turbo")
    check("no candidates: exit 2", ss.record_exit_code(rec) == 2 and rec["audio"] is None)

    # scorer failed
    rec = ss.build_record(SPEC, sweep(tmp, [701, 702]), {"error": "scoring venv not found at X; create it: ..."}, out_dir=tmp, checkpoint="turbo")
    check("no score: survivors recorded, no pick, exit 1, fix in reason",
          all(c["verdict"] == "survivor" for c in rec["candidates"]) and rec["pick"] is None
          and ss.record_exit_code(rec) == 1 and "create it" in rec["no_pick_reason"])

    # determinism failed
    rec = ss.build_record(SPEC, sweep(tmp, [701, 702]), scores(tmp, {701: 8, 702: 9}, deterministic=False), out_dir=tmp, checkpoint="turbo")
    check("determinism failed: scores kept, no pick, exit 1",
          rec["candidates"][1]["scores"]["audiobox_CE"] == 9 and rec["pick"] is None and ss.record_exit_code(rec) == 1
          and "determinism" in rec["no_pick_reason"])

    # a candidate without a score cannot be chosen
    rec = ss.build_record(SPEC, sweep(tmp, [701, 702]), scores(tmp, {701: 6.0}), out_dir=tmp, checkpoint="turbo")
    check("unscored candidate is never chosen", rec["audio"].endswith("seed701.flac"))

    # resume: an existing file is not regenerated (generate_sweep with a fake client)
    calls = []
    class FakeCC:
        DEFAULT_SERVER = "x"
        @staticmethod
        def queue(server, graph): calls.append("queue"); return "pid"
        @staticmethod
        def wait_for_history(server, pid, label=""): return {"outputs": {}}
        @staticmethod
        def download_outputs(server, hist, stem, kinds=()):
            p = Path(str(stem) + ".flac"); p.write_bytes(b"fLaC"); return [p]
    real_cc, real_pp = ss.comfy_client, ss.gs._postprocess
    ss.comfy_client = FakeCC
    ss.gs._postprocess = lambda path, ceiling: {"truncated": False, "end_decay_s": 1.0, "true_peak_dbtp": -1.0}
    try:
        rdir = tmp / "resume"; rdir.mkdir()
        (rdir / f"{SPEC['name']}_seed701.flac").write_bytes(b"fLaC")
        sw = ss.generate_sweep("x", SPEC, [701, 702], rdir, checkpoint="turbo", ceiling=-1.0)
        check("resume: existing seed not re-queued, new seed queued", calls == ["queue"] and set(sw) == {701, 702}, calls)
    finally:
        ss.comfy_client, ss.gs._postprocess = real_cc, real_pp

    # --into a fixture manifest
    mdir = tmp / "cut"; mdir.mkdir(); (mdir / "assets").mkdir()
    songdir = tmp / "song"; songdir.mkdir()
    sw = sweep(songdir, [701, 702])
    rec = ss.build_record(SPEC, sw, scores(tmp, {701: 7.0, 702: 8.0}), out_dir=songdir, checkpoint="turbo")
    (mdir / "old.flac").write_bytes(b"fLaC"); (mdir / "assets" / "s0.png").write_bytes(b"png")
    m = M.Manifest(audio="old.flac", duration=10.0, source_timeline="t.json",
                   shots=[M.Shot(index=0, section="verse", lines=[{"index": 0, "text": "x"}], t_start=0, t_end=10.0,
                                 kind="still", prompt="p", asset="assets/s0.png")])
    mpath = mdir / "m.json"; M.write(m, mpath)
    ss.apply_into(rec, mpath, songdir)
    m2 = M.from_json(mpath.read_text())
    check("into: audio points at the chosen file relative to the manifest", m2.audio == "../song/clamor_hold_the_line_seed702.flac", m2.audio)
    check("into: song block landed and validates", len(m2.song_candidates) == 2 and m2.song_pick.picked_by == "machine-auto"
          and m2.scorer_versions.get("audiobox_aesthetics") == "0.0.4")
    M.validate(m2, manifest_dir=mdir)
    check("into: manifest validates with assets on disk", True)
    # refused --into: chosen file missing on disk
    (songdir / f"{SPEC['name']}_seed702.flac").unlink()
    try:
        ss.apply_into(rec, mpath, songdir); check("into: missing chosen file refused", False)
    except M.ManifestError:
        check("into: missing chosen file refused", True)
    check("into: refused write left the manifest intact", M.from_json(mpath.read_text()).audio == m2.audio)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}"); sys.exit(1)
print("all select_song checks passed")
