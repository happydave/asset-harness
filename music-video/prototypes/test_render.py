#!/usr/bin/env python3
"""Regression checks for render.py's duration guards. Plain `python3 test_render.py`, no pytest.

Same convention as test_timeline.py / test_manifest.py: exits non-zero on failure. Needs ffmpeg on PATH
(the renderer's only dependency). Renders one tiny solid-colour segment, so it is cheap.

The guard under test is the WI 1034 hardening: a per-segment duration mismatch must raise RenderError
before assembly, instead of silently collapsing the xfade chain (the WI 1004 B-1 failure mode).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

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


def _solid_png(path: Path):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=steelblue:s=1280x720", "-frames:v", "1", str(path)], check=True)


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

    print()
    if FAILS:
        print(f"FAILED {len(FAILS)}: {', '.join(FAILS)}")
        sys.exit(1)
    print("all render-guard checks passed")


if __name__ == "__main__":
    main()
