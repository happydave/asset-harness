#!/usr/bin/env python3
"""Regression checks for repick.py. Plain `python3 test_repick.py`, no pytest.

Same convention as test_manifest.py: exits non-zero on failure. Exercises the two tool modes over
a manifest with a full candidate layer -- re-pick (promote within the recorded set, never
regenerate, refuse loudly, leave the file untouched on refusal) and the staleness audit (derive
exactly the records whose provenance no longer matches current choices). GPU-free, ffmpeg-free.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import manifest as M
import repick as R

FAILS = []
DATE = "2026-08-26"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def refuses(name, fn):
    try:
        fn()
    except R.RepickError:
        print(f"  ok   {name}")
        return
    except Exception as e:
        print(f"  FAIL {name} (raised {type(e).__name__}: {e})")
        FAILS.append(name)
        return
    print(f"  FAIL {name} (no refusal)")
    FAILS.append(name)


def _build(tmp: Path) -> M.Manifest:
    """Three shots: still with 3 candidates, plain still, and a clip chained from shot 0's still.

    All candidate files exist on disk so re-pick's at-pick-time existence check has something to
    look at; the manifest validates against `tmp`.
    """
    for f in ("a.flac", "song_alt.flac", "shot0.png", "shot0_alt.png", "shot0_culled.png",
              "shot1.png", "clip2.mp4"):
        (tmp / f).write_bytes(b"x")
    shots = [
        M.Shot(index=0, section="verse", lines=[{"index": 0, "text": "l0"}], t_start=0.0,
               t_end=4.0, kind="kenburns", prompt="p0", asset="shot0.png"),
        M.Shot(index=1, section="verse", lines=[{"index": 1, "text": "l1"}], t_start=4.0,
               t_end=8.0, kind="kenburns", prompt="p1", asset="shot1.png"),
        M.Shot(index=2, section="chorus", lines=[{"index": 2, "text": "l2"}], t_start=8.0,
               t_end=12.0, kind="video", prompt="p2", asset="clip2.mp4"),
    ]
    s0 = shots[0]
    s0.candidates = [
        M.Candidate(asset="shot0.png", verdict="chosen", recipe={"seed": 7},
                    provenance={"prompt": "p0", "lines": s0.lines}),
        M.Candidate(asset="shot0_alt.png", verdict="survivor", recipe={"seed": 5},
                    provenance={"prompt": "p0", "lines": s0.lines}),
        M.Candidate(asset="shot0_culled.png", verdict="culled", culled_by="clipscore-floor",
                    recipe={"seed": 3}, provenance={"prompt": "p0", "lines": s0.lines}),
    ]
    s0.pick = M.Pick(picked_by="machine-provisional", reason="")
    shots[2].candidates = [
        M.Candidate(asset="clip2.mp4", verdict="chosen", recipe={"seed": 11},
                    provenance={"source_shot": 0, "source_still": "shot0.png"}),
    ]
    shots[2].pick = M.Pick(picked_by="owner", reason="best motion")
    m = M.Manifest(audio="a.flac", duration=12.0, source_timeline="t.json", shots=shots)
    m.song_candidates = [
        M.Candidate(asset="a.flac", verdict="chosen", recipe={"seed": 1},
                    scores={"audiobox_ce": 7.1}, provenance={"lyrics": "v1"}),
        M.Candidate(asset="song_alt.flac", verdict="survivor", recipe={"seed": 2},
                    scores={"audiobox_ce": 6.8}),
    ]
    m.song_pick = M.Pick(picked_by="machine-auto")
    return m


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        m = _build(tmp)
        M.validate(m, manifest_dir=tmp)
        check("fixture audits clean before any change", R.audit(m) == [])

        # --- happy path: re-pick shot 0 to a recorded survivor ---
        R.repick(m, shot=0, song=False, to_asset="shot0_alt.png", by="owner",
                 reason="warmer light", manifest_dir=tmp, date=DATE)
        s0 = m.shots[0]
        check("re-pick updates the shot asset", s0.asset == "shot0_alt.png")
        check("target became chosen",
              next(c.verdict for c in s0.candidates if c.asset == "shot0_alt.png") == "chosen")
        check("former chosen became passed-over",
              next(c.verdict for c in s0.candidates if c.asset == "shot0.png") == "passed-over")
        check("new pick records picker and reason",
              s0.pick.picked_by == "owner" and s0.pick.reason == "warmer light")
        check("prior pick landed in history with its date",
              s0.pick.history == [{"asset": "shot0.png", "picked_by": "machine-provisional",
                                   "reason": "", "date": DATE}])
        try:
            M.validate(m, manifest_dir=tmp)
            print("  ok   re-picked manifest validates")
        except M.ManifestError as e:
            print(f"  FAIL re-picked manifest validates ({e})")
            FAILS.append("re-picked manifest validates")

        # --- the design's flagship composition: the downstream clip, and ONLY it, is now stale ---
        stale = R.audit(m)
        check("audit reports exactly the invalidated downstream record",
              len(stale) == 1 and stale[0]["where"] == "shot 2 clip"
              and stale[0]["field"] == "source_still"
              and stale[0]["recorded"] == "shot0.png" and stale[0]["current"] == "shot0_alt.png",
              stale)

        # --- refusals; each must leave the manifest object consistent (still validates) ---
        refuses("re-pick to an unrecorded asset refused (never regenerates)",
                lambda: R.repick(m, shot=0, song=False, to_asset="brand_new.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        refuses("re-pick to the current chosen refused as a no-op",
                lambda: R.repick(m, shot=0, song=False, to_asset="shot0_alt.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        refuses("re-pick on a shot with no candidate layer refused",
                lambda: R.repick(m, shot=1, song=False, to_asset="shot1.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        refuses("re-pick to a culled candidate refused without the override flag",
                lambda: R.repick(m, shot=0, song=False, to_asset="shot0_culled.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        refuses("re-pick out-of-range shot refused",
                lambda: R.repick(m, shot=9, song=False, to_asset="x.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        (tmp / "shot0.png").unlink()
        refuses("re-pick to a candidate whose file is gone refused",
                lambda: R.repick(m, shot=0, song=False, to_asset="shot0.png", by="owner",
                                 reason="", manifest_dir=tmp, date=DATE))
        (tmp / "shot0.png").write_bytes(b"x")

        # --- the override flag makes a culled pick deliberate, and still recorded ---
        R.repick(m, shot=0, song=False, to_asset="shot0_culled.png", by="owner",
                 reason="gate was wrong here", manifest_dir=tmp, allow_culled=True, date=DATE)
        chosen = next(c for c in m.shots[0].candidates if c.asset == "shot0_culled.png")
        check("overridden culled candidate is chosen with the gate name cleared",
              chosen.verdict == "chosen" and chosen.culled_by == "")
        check("override appended the superseded pick to history",
              len(m.shots[0].pick.history) == 2
              and m.shots[0].pick.history[1]["asset"] == "shot0_alt.png"
              and m.shots[0].pick.reason == "gate was wrong here")
        M.validate(m, manifest_dir=tmp)

        # --- song re-pick updates audio ---
        R.repick(m, shot=None, song=True, to_asset="song_alt.flac", by="owner",
                 reason="tighter chorus", manifest_dir=tmp, date=DATE)
        check("song re-pick updates manifest audio", m.audio == "song_alt.flac")
        check("song pick history records the machine-auto pick",
              m.song_pick.history == [{"asset": "a.flac", "picked_by": "machine-auto",
                                       "reason": "", "date": DATE}])
        M.validate(m, manifest_dir=tmp)

        # --- still staleness: the shot prompt moved on under the chosen still ---
        m2 = _build(tmp)
        m2.shots[0].prompt = "p0 rewritten"
        stale2 = R.audit(m2)
        check("audit flags a chosen still whose prompt moved on",
              len(stale2) == 1 and stale2[0]["where"] == "shot 0 still"
              and stale2[0]["field"] == "prompt", stale2)
        m3 = _build(tmp)
        m3.shots[0].lines = [{"index": 0, "text": "rewritten"}]
        # keep partition metadata coherent; only the lines comparison is under test
        check("audit flags a chosen still whose lines moved on",
              any(r["where"] == "shot 0 still" and r["field"] == "lines" for r in R.audit(m3)))

    # --- CLI: exit codes and file atomicity ---
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        man_path = tmp / "manifest.json"
        M.write(_build(tmp), man_path)
        here = Path(__file__).parent

        def run(*args):
            return subprocess.run([sys.executable, str(here / "repick.py"), *args],
                                  capture_output=True, text=True)

        before = man_path.read_text()
        r = run("pick", str(man_path), "--shot", "0", "--to", "nope.png", "--by", "owner")
        check("CLI refusal exits non-zero and names the refusal",
              r.returncode == 1 and "not a recorded candidate" in r.stderr, r.stderr)
        check("CLI refusal leaves the manifest file untouched", man_path.read_text() == before)

        r = run("audit", str(man_path))
        check("CLI audit exits 0 on a clean manifest and says so",
              r.returncode == 0 and "no stale records" in r.stdout, r.stdout)

        r = run("pick", str(man_path), "--shot", "0", "--to", "shot0_alt.png", "--by", "owner",
                "--reason", "warmer light", "--date", DATE)
        check("CLI pick succeeds and prints the audit",
              r.returncode == 0 and "stale record" in r.stdout, r.stdout + r.stderr)
        after = M.from_json(man_path.read_text())
        check("CLI pick rewrote the manifest", after.shots[0].asset == "shot0_alt.png")

        r = run("audit", str(man_path))
        check("CLI audit exits 1 when stale records exist",
              r.returncode == 1 and "shot 2 clip" in r.stdout, r.stdout)

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {', '.join(FAILS)}")
        sys.exit(1)
    print("all repick checks passed")


if __name__ == "__main__":
    main()
