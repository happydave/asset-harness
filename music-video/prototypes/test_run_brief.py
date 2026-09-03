#!/usr/bin/env python3
"""Checks for run_brief.py. Plain `python3 test_run_brief.py`; every stage is a fake with the real
signature, so the driver's ordering, state, pauses, resumes and re-pick handling run in under a second.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as M
import repick
import run_brief as rb
import select_song as ss
import timeline as T

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + str(detail)}")
    if not cond:
        FAILURES.append(label)


BRIEF = json.loads((Path(__file__).with_name("inputs") / "clamor_hold_the_line.brief.json").read_text())

# --- brief validation --------------------------------------------------------------------------------
rb.validate_brief(BRIEF); check("example brief validates", True)
def bad(mut, needle):
    b = json.loads(json.dumps(BRIEF)); mut(b)
    try:
        rb.validate_brief(b); return False
    except rb.BriefError as e:
        return needle in str(e)
check("bad kind refused", bad(lambda b: b["shots"][0].update(kind="gif"), "kind"))
check("video without motion refused", bad(lambda b: b["shots"][2].pop("motion"), "motion"))
check("adjacent source refused", bad(lambda b: b["shots"][2].update(source_shot=3), "WI 1160"))
check("source pointing at a video shot refused", bad(lambda b: b["shots"][2].update(source_shot=2) or b["shots"][2].update(source_shot=2), "source_shot"))
check("still without prompt refused", bad(lambda b: b["shots"][0].pop("prompt"), "prompt"))
check("bad loop refused", bad(lambda b: b.update(loop={"length": -1}), "loop"))
check("too many clip candidates refused", bad(lambda b: b["candidates"].update(clips_n=9), "clips_n"))


# --- fakes ----------------------------------------------------------------------------------------------
class FakeTools:
    def __init__(self):
        self.calls = []

    def preflight(self, stages): self.calls.append(("preflight", tuple(stages))); return 0

    def song(self, spec, seeds, out_dir):
        self.calls.append(("song", tuple(seeds)))
        out_dir.mkdir(parents=True, exist_ok=True)
        sweep = {}
        for s in seeds:
            p = out_dir / f"{spec['name']}_seed{s}.flac"; p.write_bytes(b"fLaC")
            sweep[s] = {"path": p, "qc": {"truncated": False, "end_decay_s": 1.0, "true_peak_dbtp": -1.0}}
        scores = {"scores": {f"{spec['name']}_seed{s}": {"CE": 7.0 + 0.1 * i, "CU": 7, "PC": 6, "PQ": 8} for i, s in enumerate(seeds)},
                  "controls": {"audiobox_deterministic": True}, "version": "0.0.4"}
        rec = ss.build_record(spec, sweep, scores, out_dir=out_dir, checkpoint="turbo")
        (out_dir / f"{spec['name']}.song.json").write_text(json.dumps(rec, indent=2))
        return rec

    def align(self, audio, sheet, out_stem):
        self.calls.append(("align", Path(audio).name))
        entries = T.parse_lyric_sheet(Path(sheet).read_text())
        dur = 75.0
        lines = [T.Line(index=i, section=sec, text=txt, start=round(2 + i * 4.4, 3), end=round(5 + i * 4.4, 3), confidence="high")
                 for i, (sec, txt) in enumerate(entries)]
        T.write(T.Timeline(audio=Path(audio).name, duration=dur, route="fake", lines=lines), Path(out_stem))
        return Path(out_stem).with_suffix(".timeline.json")

    def placeholder(self, path):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"\x89PNG")

    def still_sweep(self, manifest, shots, n, seed_base, run_dir):
        self.calls.append(("still_sweep", tuple(shots), n))
        run_dir.mkdir(parents=True, exist_ok=True)
        m = M.from_json(manifest.read_text()); mdir = manifest.parent
        key = {}
        for s in m.shots:
            if s.index not in shots:
                continue
            cands = []
            for j in range(n):
                p = run_dir / f"shot{s.index:02d}_seed{seed_base + j}.png"; p.write_bytes(b"\x89PNG")
                cands.append(M.Candidate(asset=str(p.relative_to(mdir)), recipe={"seed": seed_base + j},
                                         scores={"clip_letterbox": 0.33, "pickscore_letterbox": 0.19 + 0.001 * j},
                                         provenance={"prompt": s.prompt, "lines": s.lines}))
            s.candidates, s.pick = cands, None
            key[f"shot {s.index:02d}"] = {chr(65 + j): c.asset for j, c in enumerate(cands)}
        manifest.write_text(M.to_json(m, manifest_dir=mdir))
        (run_dir / "_tile_key.json").write_text(json.dumps({"run_id": run_dir.name, "shots": key}))
        (run_dir / "pick_form.md").write_text("".join(f"## shot {i:02d} — sheet\n- Pick: \n- Why: \n" for i in shots))
        return {"shots": {}, "candidates": n * len(shots), "culled": 0, "no_survivors": [], "form": str(run_dir / "pick_form.md")}

    def still_apply_form(self, manifest, run_dir):
        import cull_stills as cs
        self.calls.append(("apply_form", run_dir.name)); return cs.apply_form(manifest, run_dir, date="2026-09-02")

    def still_provisional(self, manifest):
        import cull_stills as cs
        self.calls.append(("still_provisional",)); return cs.provisional(manifest)

    def clip_sweep(self, manifest, shot, source_shot, motion, n, seed_base, run_dir):
        self.calls.append(("clip_sweep", shot, source_shot, n))
        run_dir.mkdir(parents=True, exist_ok=True)
        m = M.from_json(manifest.read_text()); mdir = manifest.parent
        s = m.shots[shot]; cands = []
        for j in range(n):
            p = run_dir / f"shot{shot:02d}_seed{seed_base + j}.mp4"; p.write_bytes(b"mp4")
            cands.append(M.Candidate(asset=str(p.relative_to(mdir)), recipe={"seed": seed_base + j}, scores={"frames": 33},
                                     provenance={"source_shot": source_shot, "source_still": m.shots[source_shot].asset, "prompt": motion}))
        s.candidates, s.pick = cands, None
        manifest.write_text(M.to_json(m, manifest_dir=mdir))
        (run_dir / "_tile_key.json").write_text(json.dumps({"run_id": run_dir.name, "shots": {f"shot {shot:02d}": {chr(65 + j): c.asset for j, c in enumerate(cands)}}}))
        (run_dir / "pick_form.md").write_text(f"## shot {shot:02d} — sheet\n- Pick: \n- Why: \n")
        return {"candidates": n, "survivors": n, "culled": []}

    def clip_provisional(self, manifest, shot):
        import clip_candidates as clc
        self.calls.append(("clip_provisional", shot)); return clc.provisional(manifest, shot)

    def render(self, manifest, out, workdir):
        self.calls.append(("render",)); out.write_bytes(b"mp4")


def names(tools):
    return [c[0] for c in tools.calls]


def run_rc(*a, **kw):
    """Like main(): a Stop becomes its exit code instead of an exception."""
    try:
        return rb.run(*a, **kw)
    except rb.Stop as e:
        return e.code


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    bpath = tmp / "brief.json"; bpath.write_text(json.dumps(BRIEF, indent=2))

    # --- provisional end to end ---
    out = tmp / "prov"; tools = FakeTools()
    rc = rb.run(bpath, out, mode="provisional", tools=tools)
    st = json.loads((out / "run.json").read_text())
    m = M.from_json((out / "clamor_hold_the_line.manifest.json").read_text())
    check("provisional: exit 0, every stage done", rc == 0 and all(v == "done" for v in st["stages"].values()), st["stages"])
    check("provisional: stage order", names(tools) == ["preflight", "song", "align", "still_sweep", "still_provisional", "clip_sweep", "clip_provisional", "render"], names(tools))
    check("provisional: preflight asked for every stage incl. clip", tools.calls[0][1] == ("song", "align", "still", "render", "clip"))
    check("provisional: song block landed, audio relative", m.audio.startswith("song/") and m.song_pick.picked_by == "machine-auto" and len(m.song_candidates) == 3)
    check("provisional: 8 shots partitioned by the brief's line counts, kinds/prompts from the brief",
          len(m.shots) == 8 and m.shots[2].kind == "video" and m.shots[0].prompt.endswith(BRIEF["style"]) and m.shots[2].prompt == BRIEF["shots"][2]["motion"])
    check("provisional: every pick is machine-provisional", all(s.pick and s.pick.picked_by == "machine-provisional" for s in m.shots))
    check("provisional: clip source is shot 4's chosen still", m.shots[2].candidates[0].provenance["source_still"] == m.shots[4].asset)
    check("provisional: loop block carried", m.loop and m.loop.length == BRIEF["loop"]["length"])
    check("provisional: nothing on the placeholder", all(s.asset != rb.PLACEHOLDER for s in m.shots))
    check("provisional: manifest validates", M.validate(m, manifest_dir=out) is None)
    check("provisional: cut written", (out / "clamor_hold_the_line.mp4").exists())
    n = len(tools.calls)
    rc = rb.run(bpath, out, mode="provisional", tools=tools)
    check("resume on a finished run calls nothing", rc == 0 and len(tools.calls) == n)

    # --- still re-pick then resume: only render, report names the shot ---
    mp = out / "clamor_hold_the_line.manifest.json"
    other = next(c.asset for c in m.shots[3].candidates if c.verdict != "chosen")
    repick.repick(M.from_json(mp.read_text()), shot=3, song=False, to_asset=other, by="owner", reason="warmer", manifest_dir=out)
    m2 = M.from_json(mp.read_text()); m2 = repick.repick(m2, shot=3, song=False, to_asset=other, by="owner", reason="warmer", manifest_dir=out, date="2026-09-02")
    mp.write_text(M.to_json(m2, manifest_dir=out))
    n = len(tools.calls)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rb.run(bpath, out, mode="provisional", tools=tools)
    check("still re-pick: resume re-renders only (no sweeps)", rc == 0 and names(tools)[n:] == ["render"], names(tools)[n:])
    check("still re-pick: report names shot 3 only", "['3']" in buf.getvalue(), buf.getvalue())
    check("still re-pick: owner pick kept, history has the provisional pick", M.from_json(mp.read_text()).shots[3].pick.picked_by == "owner"
          and M.from_json(mp.read_text()).shots[3].pick.history[0]["picked_by"] == "machine-provisional")

    # --- song re-pick then resume: alignment re-derived, shots carried over by text ---
    m3 = M.from_json(mp.read_text())
    other_song = next(c.asset for c in m3.song_candidates if c.verdict != "chosen")
    m3 = repick.repick(m3, shot=None, song=True, to_asset=other_song, by="owner", reason="tighter", manifest_dir=out, date="2026-09-02")
    mp.write_text(M.to_json(m3, manifest_dir=out))
    n = len(tools.calls); buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rb.run(bpath, out, mode="provisional", tools=tools)
    m4 = M.from_json(mp.read_text()); st = json.loads((out / "run.json").read_text())
    check("song re-pick: alignment called on the new audio, then render; no sweeps", rc == 0 and names(tools)[n:] == ["align", "render"] and tools.calls[n][1] == Path(other_song).name, names(tools)[n:])
    check("song re-pick: shots kept their candidates and picks (text unchanged)", all(s.candidates and s.pick for s in m4.shots) and m4.shots[3].pick.picked_by == "owner")
    check("song re-pick: state notes zero resets", any("shots reset []" in nte for nte in st["notes"]), st["notes"])
    check("song re-pick: audit clean after carry-over", repick.audit(m4) == [])
    check("song re-pick: report says audio changed, no shot assets", "audio changed" in buf.getvalue() and "no shot assets changed" in buf.getvalue(), buf.getvalue())

    # --- assisted: pause, fill, resume, pause, fill, resume ---
    out = tmp / "assist"; tools = FakeTools()
    rc = run_rc(bpath, out, mode="assisted", tools=tools)
    st = json.loads((out / "run.json").read_text())
    check("assisted: stops waiting after the still sweep with exit 3", rc == rb.EXIT_WAITING and st["stages"]["stills"] == "waiting" and st["stages"]["clips"] == "pending")
    form = out / "stills" / "pick_form.md"
    text = form.read_text().replace("- Pick: \n- Why: \n", "- Pick: B\n- Why: reads best\n")
    form.write_text(text)
    rc = run_rc(bpath, out, mode="assisted", tools=tools)
    st = json.loads((out / "run.json").read_text()); m = M.from_json((out / "clamor_hold_the_line.manifest.json").read_text())
    check("assisted: resume applies the form, sweeps clips, waits again", rc == rb.EXIT_WAITING and st["stages"]["stills"] == "done" and st["stages"]["clips"] == "waiting"
          and all(s.pick.picked_by == "owner" and s.pick.reason == "reads best" for s in m.shots if s.kind != "video"))
    cform = out / "clips-shot02" / "pick_form.md"
    cform.write_text(cform.read_text().replace("- Pick: \n- Why: \n", "- Pick: A\n- Why: the flare moves\n"))
    rc = run_rc(bpath, out, mode="assisted", tools=tools)
    m = M.from_json((out / "clamor_hold_the_line.manifest.json").read_text())
    check("assisted: final resume renders with the owner's clip pick", rc == 0 and m.shots[2].pick.picked_by == "owner" and (out / "clamor_hold_the_line.mp4").exists())
    check("assisted: no provisional calls ever", "still_provisional" not in names(tools) and "clip_provisional" not in names(tools))

    # --- brief change guard ---
    b2 = json.loads(json.dumps(BRIEF)); b2["shots"][5]["prompt"] = "a different scene"; bpath2 = tmp / "brief2.json"; bpath2.write_text(json.dumps(b2))
    try:
        rb.run(bpath2, out, mode="assisted", tools=tools); check("changed brief refused without the flag", False)
    except rb.Stop as e:
        check("changed brief refused without the flag", "brief changed" in str(e))
    n = len(tools.calls)
    rc = rb.run(bpath2, out, mode="provisional", tools=tools, accept_brief_change=True)
    m = M.from_json((out / "clamor_hold_the_line.manifest.json").read_text())
    check("accepted brief change: only the changed shot is re-swept, then render", rc == 0 and ("still_sweep", (5,), 3) in tools.calls[n:] and names(tools)[n:].count("still_sweep") == 1
          and m.shots[5].pick.picked_by == "machine-provisional" and m.shots[0].pick.picked_by == "owner", tools.calls[n:])

    # --- low-confidence timeline stops the run unless allowed ---
    class LowAlign(FakeTools):
        def align(self, audio, sheet, out_stem):
            p = super().align(audio, sheet, out_stem)
            tl = T.from_json(p.read_text())
            for l in tl.lines[8:]:
                l.confidence = "low"
            T.write(tl, Path(out_stem)); return p
    try:
        rb.run(bpath, tmp / "low", mode="provisional", tools=LowAlign()); check("low-confidence timeline stops the run", False)
    except rb.Stop as e:
        check("low-confidence timeline stops the run with tap + re-pick remedies", "LOW confidence" in str(e) and "tap_align" in str(e) and "repick.py" in str(e))
    rc = rb.run(bpath, tmp / "low", mode="provisional", tools=LowAlign(), allow_low_confidence=True)
    check("--allow-low-confidence proceeds", rc == 0)
    class OneLow(LowAlign):
        def align(self, audio, sheet, out_stem):
            p = FakeTools.align(self, audio, sheet, out_stem)
            tl = T.from_json(p.read_text()); tl.lines[3].confidence = "low"; T.write(tl, Path(out_stem)); return p
    rc = rb.run(bpath, tmp / "onelow", mode="provisional", tools=OneLow())
    check("a single low line is a warning, not a stop", rc == 0)

    # --- placeholder guard + preflight failure ---
    class FailingPreflight(FakeTools):
        def preflight(self, stages): return 1
    try:
        rb.run(bpath, tmp / "pf", mode="provisional", tools=FailingPreflight()); check("preflight failure stops the run", False)
    except rb.Stop as e:
        check("preflight failure stops the run", "preflight FAILED" in str(e) and e.code == 1)
    class NoPickSong(FakeTools):
        def song(self, spec, seeds, out_dir):
            rec = super().song(spec, seeds, out_dir); rec["pick"] = None; rec["audio"] = None; rec["no_pick_reason"] = "scorer down"
            for c in rec["candidates"]: c["verdict"] = "survivor"
            return rec
    try:
        rb.run(bpath, tmp / "np", mode="provisional", tools=NoPickSong()); check("song no-pick stops the run", False)
    except rb.Stop as e:
        check("song no-pick stops the run with the reason", "NO PICK" in str(e) and "scorer down" in str(e))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}"); sys.exit(1)
print("all run_brief checks passed")
