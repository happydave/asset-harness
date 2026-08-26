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
        check("loop.blend_at defaults to end", M.Loop(length=20.0).blend_at == "end")
        raises("bad loop.blend_at rejected", bad_loop(length=20.0, blend_at="middle"))
        back2 = M.from_json(M.to_json(m, manifest_dir=tmp))
        check("loop.blend_at round-trips", back2.loop.blend_at == "end", back2.loop)

    # --- candidate layer (WI 1175) ---
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # Byte-identity: a candidate-free manifest serializes EXACTLY as the pre-1175 code did
        # (expected string captured from that code before this layer landed), so no shipped
        # manifest churns on rewrite.
        fix_shots = [
            M.Shot(index=0, section="verse", lines=[{"index": 0, "text": "line 0"}], t_start=0.0,
                   t_end=4.0, kind="kenburns", prompt="p0", asset="s0.png"),
            M.Shot(index=1, section="chorus", lines=[{"index": 1, "text": "line 1"}], t_start=4.0,
                   t_end=8.0, kind="still", prompt="p1", asset="s1.png"),
        ]
        fix = M.Manifest(audio="a.flac", duration=8.0, source_timeline="t.json", shots=fix_shots,
                         loop=M.Loop(length=6.0))
        expected = (
            '{\n  "audio": "a.flac",\n  "duration": 8.0,\n  "source_timeline": "t.json",\n'
            '  "shots": [\n    {\n      "index": 0,\n      "section": "verse",\n      "lines": [\n'
            '        {\n          "index": 0,\n          "text": "line 0"\n        }\n      ],\n'
            '      "t_start": 0.0,\n      "t_end": 4.0,\n      "kind": "kenburns",\n'
            '      "prompt": "p0",\n      "asset": "s0.png",\n      "kb": {\n'
            '        "zoom": "in",\n        "pan": "c"\n      }\n    },\n    {\n'
            '      "index": 1,\n      "section": "chorus",\n      "lines": [\n        {\n'
            '          "index": 1,\n          "text": "line 1"\n        }\n      ],\n'
            '      "t_start": 4.0,\n      "t_end": 8.0,\n      "kind": "still",\n'
            '      "prompt": "p1",\n      "asset": "s1.png",\n      "kb": {\n'
            '        "zoom": "in",\n        "pan": "c"\n      }\n    }\n  ],\n  "notes": "",\n'
            '  "loop": {\n    "length": 6.0,\n    "crossfade": 0.75,\n    "search": 0.0,\n'
            '    "blend_at": "end"\n  }\n}\n')
        check("candidate-free manifest serializes byte-identically to pre-1175 output",
              M.to_json(fix) == expected)
        check("pre-1175 JSON loads with an empty candidate layer",
              M.from_json(expected).shots[0].candidates == []
              and M.from_json(expected).shots[0].pick is None
              and M.from_json(expected).song_pick is None)

        def _with_candidates():
            m = _good_manifest(tmp)
            s0 = m.shots[0]
            s0.candidates = [
                M.Candidate(asset="shot0_bad.png", verdict="culled", culled_by="clipscore-floor",
                            recipe={"seed": 3}, provenance={"prompt": s0.prompt,
                                                            "lines": s0.lines}),
                M.Candidate(asset="shot0_alt.png", verdict="survivor",
                            recipe={"seed": 5}, scores={"pickscore": 0.41},
                            provenance={"prompt": s0.prompt, "lines": s0.lines}),
                M.Candidate(asset=s0.asset, verdict="chosen", recipe={"seed": 7},
                            scores={"pickscore": 0.44},
                            provenance={"prompt": s0.prompt, "lines": s0.lines}),
            ]
            s0.pick = M.Pick(picked_by="owner", reason="warmest light")
            m.song_candidates = [
                M.Candidate(asset=m.audio, verdict="chosen", recipe={"seed": 1},
                            scores={"audiobox_ce": 7.1, "qc_flags": []},
                            provenance={"lyrics": "v1"}),
                M.Candidate(asset="song_alt.flac", verdict="passed-over", recipe={"seed": 2},
                            scores={"audiobox_ce": 6.8, "qc_flags": []}),
            ]
            m.song_pick = M.Pick(picked_by="machine-auto")
            m.scorer_versions = {"pickscore": "v2", "audiobox": "0.3"}
            return m

        mc = _with_candidates()
        try:
            M.validate(mc, manifest_dir=tmp)
            print("  ok   candidate layer validates")
        except M.ManifestError as e:
            print(f"  FAIL candidate layer validates ({e})")
            FAILS.append("candidate layer validates")
        back = M.from_json(M.to_json(mc, manifest_dir=tmp))
        check("candidate layer round-trips",
              len(back.shots[0].candidates) == 3
              and back.shots[0].candidates[0].culled_by == "clipscore-floor"
              and back.shots[0].candidates[2].recipe == {"seed": 7}
              and back.shots[0].pick.reason == "warmest light"
              and back.song_pick.picked_by == "machine-auto"
              and back.scorer_versions == {"pickscore": "v2", "audiobox": "0.3"})

        def bad_cands(mutate):
            mm = _with_candidates()
            mutate(mm)
            return lambda: M.validate(mm, manifest_dir=tmp)

        def _set(mm, **kw):
            for k, v in kw.items():
                setattr(mm.shots[0].candidates[2], k, v)

        raises("verdict outside the closed set rejected",
               bad_cands(lambda mm: _set(mm, verdict="maybe")))
        raises("culled without a gate name rejected",
               bad_cands(lambda mm: _set(mm, verdict="culled", culled_by="")))
        raises("culled_by on a non-culled candidate rejected",
               bad_cands(lambda mm: mm.shots[0].candidates[1].__setattr__("culled_by", "gate")))
        raises("chosen asset != shot asset rejected",
               bad_cands(lambda mm: _set(mm, asset="somewhere_else.png")))
        raises("two chosen in one set rejected",
               bad_cands(lambda mm: mm.shots[0].candidates[1].__setattr__("verdict", "chosen")))
        raises("a pick with zero chosen rejected",
               bad_cands(lambda mm: _set(mm, verdict="survivor")))
        raises("a chosen with no pick rejected",
               bad_cands(lambda mm: setattr(mm.shots[0], "pick", None)))
        raises("picked_by outside the closed set rejected",
               bad_cands(lambda mm: mm.shots[0].pick.__setattr__("picked_by", "vibes")))
        raises("duplicate candidate assets rejected",
               bad_cands(lambda mm: mm.shots[0].candidates[1].__setattr__("asset", "shot0_bad.png")))
        raises("song chosen != audio rejected",
               bad_cands(lambda mm: mm.song_candidates[0].__setattr__("asset", "other.flac")))
        raises("provenance.source_shot out of range rejected",
               bad_cands(lambda mm: _set(mm, provenance={"source_shot": 99})))

        # mid-stage: candidates recorded, no pick yet, no chosen -- must NOT be rejected
        mid = _with_candidates()
        mid.shots[0].candidates[2].verdict = "survivor"
        mid.shots[0].pick = None
        try:
            M.validate(mid, manifest_dir=tmp)
            print("  ok   pickless candidate set (mid-stage) passes")
        except M.ManifestError as e:
            print(f"  FAIL pickless candidate set (mid-stage) passes ({e})")
            FAILS.append("pickless candidate set (mid-stage) passes")

        # --- adjacency lint (WI 1160 rule): video shot next to its own source still ---
        def _clip_at(idx, src_still):
            mm = _good_manifest(tmp)
            s = mm.shots[idx]
            s.kind = "video"
            (tmp / "clip.mp4").write_bytes(b"x")
            s.asset = "clip.mp4"
            s.candidates = [M.Candidate(asset="clip.mp4", verdict="chosen",
                                        provenance={"source_shot": 0,
                                                    "source_still": src_still})]
            s.pick = M.Pick(picked_by="owner")
            return mm

        raises("video clip adjacent to its own source still rejected",
               lambda: M.validate(_clip_at(1, "shot0.png"), manifest_dir=tmp))
        try:
            M.validate(_clip_at(2, "shot0.png"), manifest_dir=tmp)
            print("  ok   non-adjacent source still passes the lint")
        except M.ManifestError as e:
            print(f"  FAIL non-adjacent source still passes the lint ({e})")
            FAILS.append("non-adjacent source still passes the lint")
        no_prov = _clip_at(1, "shot0.png")
        no_prov.shots[1].candidates[0].provenance = {}
        try:
            M.validate(no_prov, manifest_dir=tmp)
            print("  ok   lint skips a clip that recorded no source (evidence-driven)")
        except M.ManifestError as e:
            print(f"  FAIL lint skips a clip that recorded no source ({e})")
            FAILS.append("lint skips a clip that recorded no source (evidence-driven)")

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {', '.join(FAILS)}")
        sys.exit(1)
    print("all manifest checks passed")


if __name__ == "__main__":
    main()
