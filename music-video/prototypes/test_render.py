#!/usr/bin/env python3
"""Regression checks for render.py's duration guards. Plain `python3 test_render.py`, no pytest.

Same convention as test_timeline.py / test_manifest.py: exits non-zero on failure. Needs ffmpeg on PATH
(the renderer's only dependency). Renders one tiny solid-colour segment, so it is cheap.

The guard under test is the WI 1034 hardening: a per-segment duration mismatch must raise RenderError
before assembly, instead of silently collapsing the xfade chain (the WI 1004 B-1 failure mode).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import manifest as M
import render as R

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def raises(name, fn, exc=R.RenderError):
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


def _solid_png(path: Path, colour="steelblue"):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"color=c={colour}:s=1280x720", "-frames:v", "1", str(path)], check=True)


def _sine_flac(path: Path, seconds: float):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=220:sample_rate=44100:duration={seconds}",
                    str(path)], check=True)


def _tiny_manifest(tmp: Path, duration: float, loop=None):
    """Two shots over a short sine, with real assets on disk."""
    _solid_png(tmp / "s0.png", "steelblue")
    _solid_png(tmp / "s1.png", "seagreen")
    _sine_flac(tmp / "song.flac", duration)
    half = round(duration / 2, 3)
    shots = [
        M.Shot(index=0, section="verse", lines=[], t_start=0.0, t_end=half, kind="kenburns",
               prompt="p0", asset="s0.png"),
        M.Shot(index=1, section="verse", lines=[], t_start=half, t_end=duration, kind="kenburns",
               prompt="p1", asset="s1.png"),
    ]
    return M.Manifest(audio="song.flac", duration=duration, source_timeline="t.json", shots=shots,
                      loop=loop)


def main():
    if not subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0:
        print("SKIP: ffmpeg not on PATH")
        return

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        img = tmp / "solid.png"
        _solid_png(img)
        seg = tmp / "seg.mp4"
        target = 2.0
        R._render_still_segment(img, {"zoom": "in", "pan": "c"}, target, seg)

        # the segment renders to its target length (this is what B-1 broke: it came out ~0.83x short)
        measured = R._probe_duration(seg)
        check("still segment renders to target duration",
              abs(measured - target) <= R.DUR_TOL, f"target {target} got {measured}")

        # video-stream duration helper agrees (frames / FPS)
        vdur = R._probe_video_duration(seg)
        check("video-stream duration matches", abs(vdur - target) <= R.DUR_TOL, f"got {vdur}")

        # the guard PASSES on a correct segment ...
        try:
            R._assert_duration(seg, target, "correct segment")
            print("  ok   guard passes on a correct segment")
        except R.RenderError as e:
            print(f"  FAIL guard passes on a correct segment ({e})")
            FAILS.append("guard passes on a correct segment")

        # ... and FIRES when the segment is not the asked-for length. A ~0.83x short segment is exactly
        # the B-1 shape; assert against a longer expected to simulate "segment came out short".
        raises("guard rejects a short segment",
               lambda: R._assert_duration(seg, target / 0.83, "short segment"))
        raises("guard rejects a long segment",
               lambda: R._assert_duration(seg, target * 1.5, "long segment"))

        # a mismatch within tolerance (sub-2-frame) must NOT fire (no false positive on quantisation)
        try:
            R._assert_duration(seg, target + (1.0 / R.FPS), "within-tolerance")
            print("  ok   guard tolerates sub-frame quantisation")
        except R.RenderError as e:
            print(f"  FAIL guard tolerates sub-frame quantisation ({e})")
            FAILS.append("guard tolerates sub-frame quantisation")

    # --- the loop block emits a SECOND artifact and leaves the first alone (WI 1159) ---
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        dur = 4.0
        plain = _tiny_manifest(tmp, dur)
        R.render(plain, tmp, tmp / "plain.mp4", tmp / "work_plain")
        looped = _tiny_manifest(tmp, dur, loop=M.Loop(length=3.0, crossfade=0.3))
        R.render(looped, tmp, tmp / "cut.mp4", tmp / "work_loop")

        loop_out = tmp / "cut_loop.mp4"
        check("the loop cut is written alongside the full cut", loop_out.is_file())
        check("the loop report is written next to it", (tmp / "cut_loop.loop.json").is_file())
        check("the full cut is unchanged by the loop block",
              abs(R._probe_video_duration(tmp / "cut.mp4")
                  - R._probe_video_duration(tmp / "plain.mp4")) < 1e-6,
              f"{R._probe_video_duration(tmp / 'cut.mp4')} vs "
              f"{R._probe_video_duration(tmp / 'plain.mp4')}")
        check("the full cut still reaches the song duration",
              abs(R._probe_video_duration(tmp / "cut.mp4") - dur) <= 3.0 / R.FPS)
        check("the loop cut is the loop length, not the full length",
              abs(R._probe_video_duration(loop_out) - 3.0) <= 1.0 / R.FPS,
              str(R._probe_video_duration(loop_out)))
        rep = json.loads((tmp / "cut_loop.loop.json").read_text())
        check("the report records where the dissolve was placed",
              rep["blend_at"] == "end", str(rep.get("blend_at")))
        check("a loop point clear of the shot dissolves carries no note",
              rep["shot_boundary_note"] is None, str(rep["shot_boundary_note"]))

        # ... and one that lands ON the shot boundary does carry it.
        on_seam = _tiny_manifest(tmp, dur, loop=M.Loop(length=2.0, crossfade=0.3))
        R.render(on_seam, tmp, tmp / "seam.mp4", tmp / "work_seam")
        rep2 = json.loads((tmp / "seam_loop.loop.json").read_text())
        check("a loop point inside a shot dissolve is flagged in the report",
              rep2["shot_boundary_note"] is not None and "2.0s" in rep2["shot_boundary_note"],
              str(rep2["shot_boundary_note"]))

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {', '.join(FAILS)}")
        sys.exit(1)
    print("all render-guard checks passed")


if __name__ == "__main__":
    main()
