#!/usr/bin/env python3
"""Regression checks for manifest.py. Plain `python3 test_manifest.py`, no pytest.

Same convention as test_timeline.py: a script that exits non-zero on failure, so it gates without a
dependency. Exercises the *partition and validation* logic -- the part that must refuse a broken
manifest before it reaches the renderer (a gap that renders black, a missing asset, a bad kind).
"""
import sys
import tempfile
from pathlib import Path

import manifest as M
import timeline as T

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def raises(name, fn, exc=M.ManifestError):
    try:
        fn()
    except exc:
        print(f"  ok   {name}")
        return
    except Exception as e:
        print(f"  FAIL {name} (raised {type(e).__name__}: {e})")
        FAILS.append(name)
        return
    print(f"  FAIL {name} (no exception)")
    FAILS.append(name)


def _timeline(n=6, dur=30.0):
    lines = []
    for i in range(n):
        start = 2.0 + i * 4.0
        lines.append(T.Line(index=i, section="chorus" if i % 2 else "verse",
                            text=f"line {i}", start=start, end=start + 3.0, confidence="high"))
    return T.Timeline(audio="x.flac", duration=dur, route="test", lines=lines)


def _good_manifest(tmp: Path, n_shots=3):
    """A valid manifest with real (empty) asset + audio files under tmp."""
    tl = _timeline(n=n_shots * 2)
    shots = M.partition_shots(tl, [2] * n_shots)
    (tmp / "a.flac").write_bytes(b"x")
    for s in shots:
        s.kind = "kenburns"
        s.prompt = f"prompt {s.index}"
        s.asset = f"shot{s.index}.png"
        (tmp / s.asset).write_bytes(b"x")
    return M.Manifest(audio="a.flac", duration=tl.duration, source_timeline="t.json", shots=shots)


def main():
    tl = _timeline(n=6, dur=30.0)

    # --- partition ---
    shots = M.partition_shots(tl, [2, 2, 2])
    check("partition shot count", len(shots) == 3)
    check("shot0 starts at 0", shots[0].t_start == 0.0, shots[0].t_start)
    check("last shot ends at duration", shots[-1].t_end == 30.0, shots[-1].t_end)
    contiguous = all(abs(shots[i].t_end - shots[i + 1].t_start) < M.EPS for i in range(len(shots) - 1))
    check("partition is contiguous", contiguous)
    check("shot carries its lines", shots[1].lines[0]["index"] == 2)
    raises("partition rejects wrong group sum", lambda: M.partition_shots(tl, [2, 2]))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # --- happy path ---
        good = _good_manifest(tmp)
        try:
            M.validate(good, manifest_dir=tmp)
            print("  ok   valid manifest passes")
        except M.ManifestError as e:
            print(f"  FAIL valid manifest passes ({e})")
            FAILS.append("valid manifest passes")

        # round-trip
        txt = M.to_json(good, manifest_dir=tmp)
        back = M.from_json(txt)
        check("json round-trip preserves shots", len(back.shots) == len(good.shots))
        check("json round-trip preserves kind", back.shots[0].kind == "kenburns")

        # --- negative: missing asset ---
        m = _good_manifest(tmp)
        m.shots[1].asset = "does_not_exist.png"
        raises("missing asset rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: gap in partition ---
        m = _good_manifest(tmp)
        m.shots[1].t_start += 1.0  # opens a gap after shot0
        raises("gap in partition rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: bad kind ---
        m = _good_manifest(tmp)
        m.shots[0].kind = "hologram"
        raises("bad kind rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: shot0 not at 0 ---
        m = _good_manifest(tmp)
        m.shots[0].t_start = 1.0
        raises("shot0 must start at 0", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: last shot != duration ---
        m = _good_manifest(tmp)
        m.shots[-1].t_end = 25.0
        raises("last shot must reach duration", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: empty prompt ---
        m = _good_manifest(tmp)
        m.shots[2].prompt = "   "
        raises("empty prompt rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: missing audio ---
        m = _good_manifest(tmp)
        m.audio = "no_song.flac"
        raises("missing audio rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- negative: bad kb ---
        m = _good_manifest(tmp)
        m.shots[0].kb = {"zoom": "sideways", "pan": "c"}
        raises("bad kb.zoom rejected", lambda: M.validate(m, manifest_dir=tmp))

        # --- loop block (WI 1159) ---
        check("loop is absent by default", _good_manifest(tmp).loop is None)
        m = _good_manifest(tmp)
        m.loop = M.Loop(length=20.0, crossfade=0.75, search=2.0)
        try:
            M.validate(m, manifest_dir=tmp)
            print("  ok   valid loop block passes")
        except M.ManifestError as e:
            print(f"  FAIL valid loop block passes ({e})")
            FAILS.append("valid loop block passes")
        back = M.from_json(M.to_json(m, manifest_dir=tmp))
        check("loop block round-trips", back.loop is not None and back.loop.length == 20.0
              and back.loop.crossfade == 0.75 and back.loop.search == 2.0, back.loop)
        no_loop = M.from_json(M.to_json(_good_manifest(tmp), manifest_dir=tmp))
        check("a manifest written without a loop block still loads", no_loop.loop is None)

        def bad_loop(**kw):
            mm = _good_manifest(tmp)
            mm.loop = M.Loop(**kw)
            return lambda: M.validate(mm, manifest_dir=tmp)

        raises("loop.length must be positive", bad_loop(length=0.0))
        raises("loop.crossfade must be positive", bad_loop(length=20.0, crossfade=0.0))
        raises("loop.search must not be negative", bad_loop(length=20.0, search=-1.0))
        raises("loop.search past the start rejected", bad_loop(length=20.0, search=20.0))
        raises("loop.crossfade >= shortest candidate rejected",
               bad_loop(length=20.0, crossfade=3.0, search=18.0))
        raises("loop longer than the cut rejected", bad_loop(length=29.9, crossfade=0.75))

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {', '.join(FAILS)}")
        sys.exit(1)
    print("all manifest checks passed")


if __name__ == "__main__":
    main()
