#!/usr/bin/env python3
"""Checks for loop_finish.py (WI 1159). Plain `python3 test_loop.py`, no pytest, no GPU.

Synthetic sources only, built with ffmpeg:
  * a GREY-RAMP video whose frame N is a uniform grey of value N, so frame identity is readable as a
    byte and needs no similarity threshold (SSIM through a PNG round-trip is NOT usable for this —
    colour-range retagging makes byte-identical frames score ~0.83; see the work item's plan.md);
  * audio whose level ramps, so a plain trim is a real negative control rather than a lucky pass.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop_finish as lf

FAILURES: list[str] = []
CHECKS = 0
FPS = 30
GREY_TOL = 3          # h264 at crf 26 shifts a uniform grey by a step or two


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILURES.append(f"{name} {detail}")


def raises(name: str, fn, *, want: str = "") -> None:
    try:
        fn()
    except lf.LoopError as e:
        check(name, want in str(e), f"message was {str(e)!r}, wanted {want!r}")
    except Exception as e:                                    # noqa: BLE001 - report the wrong type
        check(name, False, f"raised {type(e).__name__}: {e}")
    else:
        check(name, False, "did not raise")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"fixture build failed: {' '.join(cmd[:6])}...\n{r.stderr[-500:]}")


# 1320.25 cycles in 6 s: a sine that starts at zero crossing and sits at its PEAK at t = 6.0, so a plain
# trim there is a genuine waveform discontinuity rather than a lucky in-phase cut.
MIDCYCLE_HZ = 1320.25 / 6.0


def grey_ramp_source(dst: Path, seconds: int = 10, ramp_audio: bool = False,
                     freq: float = 220.0) -> Path:
    """Frame N is a uniform grey of value N mod 250; audio is a sine, optionally ramping in level."""
    vol = "pow(t/%d\\,2)" % seconds if ramp_audio else "0.5"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-i", f"nullsrc=s=320x180:r={FPS}:d={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=44100:duration={seconds}",
         "-vf", "format=gray,geq=lum='mod(N,250)'",
         "-af", f"volume='{vol}':eval=frame",
         "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dst)])
    return dst


def luma(clip: Path, n: int) -> int:
    """The first luma byte of frame `n` — exact frame identity on a grey-ramp source."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"select=eq(n\\,{n})",
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    if not r.stdout:
        raise SystemExit(f"could not read frame {n} of {clip}")
    return r.stdout[0]


def hard_trim(src: Path, dst: Path, length: float) -> Path:
    """The thing the wrap replaces: a plain trim, whose end and start are unrelated material."""
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-t", f"{length:.6f}",
         *lf.MP4_ARGS, str(dst)])
    return dst


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="loop_test_", dir=Path(__file__).resolve().parent / "outputs"))
    try:
        print("parameter validation")
        raises("rejects non-positive length",
               lambda: lf.check_params(10, 0, 0.5, 0), want="length must be positive")
        raises("rejects non-positive crossfade",
               lambda: lf.check_params(10, 6, 0, 0), want="crossfade must be positive")
        raises("rejects negative search",
               lambda: lf.check_params(10, 6, 0.5, -1), want="must not be negative")
        raises("rejects search >= length",
               lambda: lf.check_params(10, 6, 0.5, 6), want="runs past the start")
        raises("rejects crossfade >= shortest candidate",
               lambda: lf.check_params(10, 6, 2.0, 4.5), want="not shorter than")
        raises("rejects a source too short for the wrap",
               lambda: lf.check_params(6.2, 6, 0.5, 0), want="the wrap needs")
        check("accepts a workable set", lf.check_params(10, 6, 0.5, 2) is None)

        print("envelope matching")
        env = [(1.0 if i % 100 == 0 else 0.1) for i in range(1000)]   # a hit every 100 frames = 1 s
        check("identical windows score 0", lf.envelope_distance(env, 0, 50) == 0.0)
        check("out-of-phase windows score worse",
              lf.envelope_distance(env, 50, 50) > lf.envelope_distance(env, 100, 50))
        raises("refuses a window past the end of the envelope",
               lambda: lf.envelope_distance(env, 990, 50), want="envelope too short")

        print("loop-point search")
        got = lf.choose_length(env, length=6.0, crossfade=0.5, search=2.0, fps=FPS)
        check("search stays inside the backwards window",
              4.0 <= got["length"] <= 6.0, f"chose {got['length']}")
        check("search lands on a whole video frame",
              abs(got["length"] * FPS - round(got["length"] * FPS)) < 1e-9, str(got["length"]))
        check("search lands a whole number of periods back from the authored length",
              abs((6.0 - got["length"]) - round(6.0 - got["length"])) < 1e-9,
              f"chose {got['length']}, offset {6.0 - got['length']}")
        check("search reports the authored point's score for comparison",
              got["authored_distance"] is not None and got["candidates"] == 61,
              str(got["candidates"]))
        exact = lf.choose_length(env, length=6.0, crossfade=0.5, search=0.0, fps=FPS)
        check("search=0 uses the authored length unchanged",
              exact["length"] == 6.0 and exact["candidates"] == 1, str(exact))
        frac = lf.choose_length(env, length=6.017, crossfade=0.5, search=0.0, fps=FPS)
        check("a fractional length is quantised to whole frames",
              frac["frames"] == 181 and abs(frac["length"] - 181 / FPS) < 1e-4, str(frac))

        print("wrap composition, blend at the start (grey-ramp fixture)")
        src = grey_ramp_source(tmp / "src.mp4")
        out = tmp / "src_loop.mp4"
        report = lf.finish(src, out, length=6.0, crossfade=0.5, blend_at="start",
                           workdir=tmp / "work")
        check("output is exactly length x fps frames", report["video"]["frames"] == 180,
              str(report["video"]["frames"]))
        check("output frame 0 is the tail's first frame, at full weight",
              abs(luma(out, 0) - luma(src, 180)) <= GREY_TOL,
              f"{luma(out, 0)} vs {luma(src, 180)}")
        check("the head resumes untouched once the blend ends",
              abs(luma(out, 15) - luma(src, 15)) <= GREY_TOL, f"{luma(out, 15)} vs {luma(src, 15)}")
        check("mid-blend frames are neither side",
              min(luma(src, 1), luma(src, 181)) < luma(out, 1) < max(luma(src, 1), luma(src, 181)),
              f"out[1]={luma(out, 1)} between {luma(src, 1)} and {luma(src, 181)}")
        check("the last output frame is the source frame before the loop point",
              abs(luma(out, 179) - luma(src, 179)) <= GREY_TOL,
              f"{luma(out, 179)} vs {luma(src, 179)}")

        print("join gates")
        check("the wrapped loop passes every gate", report["pass"] is True, str(report))
        check("video join is no worse than the local norm",
              report["video"]["gap"] <= lf.SEAM_TOLERANCE, str(report["video"]))
        check("audio discontinuity is within the local maximum",
              report["audio"]["discontinuity_pass"], str(report["audio"]))
        check("codec padding is measured, not assumed",
              isinstance(report["audio"]["codec_padding_samples"], int)
              and report["audio"]["codec_padding_samples"] >= 0,
              str(report["audio"]["codec_padding_samples"]))
        check("the video gate is the WI 1160 gate, not a second opinion",
              lf.SEAM_TOLERANCE == 0.05 and lf.SEAM_WINDOW == 8)
        check("the join is compared against a keyframe boundary too, not only its neighbours",
              report["video"]["keyframe_norm"] is not None
              and report["video"]["keyframe_gap"] is not None, str(report["video"]))
        check("interior keyframes are found on a varied clip",
              len(lf.keyframe_boundaries(out)) > 0, str(lf.keyframe_boundaries(out)))

        # A clip with nothing to cut on carries a single keyframe, so the fair-comparison norm has no
        # sample: the gate must fall back to the local norm rather than crash or pass vacuously.
        static = tmp / "static.mp4"
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"color=c=steelblue:s=320x180:r={FPS}:d=8", "-c:v", "libx264", "-crf", "26",
             "-pix_fmt", "yuv420p", str(static)])
        check("a clip with no interior keyframe has no keyframe norm to offer",
              lf.keyframe_boundaries(static) == [], str(lf.keyframe_boundaries(static)))
        sv = lf.video_join(static, tmp / "work_static")
        check("and the gate falls back to the local norm",
              sv["keyframe_norm"] is None and sv["pass"], str(sv))

        print("negative controls")
        ramp = grey_ramp_source(tmp / "ramp.mp4", ramp_audio=True)
        trimmed = hard_trim(ramp, tmp / "ramp_trim.mp4", 6.0)
        v = lf.video_join(trimmed, tmp / "work_trim")
        a = lf.audio_join(trimmed, 6.0, tmp / "work_trim")
        check("a hard trim FAILS the video join gate", not v["pass"], str(v))
        check("a hard trim FAILS the audio level gate", not a["level_pass"], str(a))
        # Wrapping does NOT rescue this one, and should not claim to: a crossfade bridges a level step,
        # it cannot remove it. The loud end of this source still lands on its near-silent start.
        wrapped = lf.finish(ramp, tmp / "ramp_loop.mp4", length=6.0, crossfade=0.5,
                            blend_at="start", workdir=tmp / "work_ramp")
        check("wrapping does not rescue a genuine level mismatch",
              not wrapped["audio"]["level_pass"], str(wrapped["audio"]))
        check("but it does fix the discontinuity the trim had",
              wrapped["audio"]["discontinuity_pass"], str(wrapped["audio"]))

        # The level control above cuts into near-silence, which the discontinuity check cannot see
        # (both ends land near a zero crossing). This one isolates it: constant level, trimmed at the
        # sine's peak.
        mid = grey_ramp_source(tmp / "mid.mp4", freq=MIDCYCLE_HZ)
        mid_trim = hard_trim(mid, tmp / "mid_trim.mp4", 6.0)
        ma = lf.audio_join(mid_trim, 6.0, tmp / "work_mid")
        check("a mid-cycle trim FAILS the discontinuity gate",
              not ma["discontinuity_pass"] and ma["level_pass"], str(ma))
        check("the discontinuity failure is decisive, not marginal",
              ma["discontinuity_ratio"] > 10, str(ma["discontinuity_ratio"]))
        mid_wrap = lf.finish(mid, tmp / "mid_loop.mp4", length=6.0, crossfade=0.5,
                             blend_at="start", workdir=tmp / "work_midw")
        check("the same mid-cycle source WRAPPED passes the discontinuity gate",
              mid_wrap["audio"]["discontinuity_pass"], str(mid_wrap["audio"]))

        print("blend at the end (WI 1181)")
        # `start` opens mid-dissolve on material from the end of the cut; `end` opens clean. Both are
        # the same cycle, so both must loop — only the single pass differs.
        end_out = tmp / "src_end.mp4"
        end_rep = lf.finish(src, end_out, length=6.0, crossfade=0.5, blend_at="end",
                            workdir=tmp / "work_end")
        xf = 15                                             # 0.5 s at 30 fps
        check("end is the default arrangement",
              lf.finish.__kwdefaults__["blend_at"] == "end" and lf.BLEND_AT[0] == "end")
        check("the end arrangement is still exactly the loop length",
              end_rep["video"]["frames"] == 180, str(end_rep["video"]["frames"]))
        check("a single pass opens on clean material, not on the end of the cut",
              abs(luma(end_out, 0) - luma(src, xf)) <= GREY_TOL,
              f"{luma(end_out, 0)} vs src[{xf}]={luma(src, xf)}")
        check("the last frame is EXACTLY the frame before the opening one",
              abs(luma(end_out, 179) - luma(src, xf - 1)) <= GREY_TOL,
              f"{luma(end_out, 179)} vs src[{xf - 1}]={luma(src, xf - 1)} — a naive rotation would "
              f"leave a ghost of the outgoing shot here")
        check("the dissolve now sits at the end of the file",
              abs(luma(end_out, 164) - luma(src, 179)) <= GREY_TOL
              and not abs(luma(end_out, 165) - luma(src, 180)) <= GREY_TOL,
              f"mid ends {luma(end_out, 164)}, blend starts {luma(end_out, 165)}")
        check("outside the dissolve the two arrangements are one cycle, rotated",
              all(abs(luma(end_out, i) - luma(out, (i + xf) % 180)) <= GREY_TOL
                  for i in (0, 40, 100, 164)),
              "sampled frames 0/40/100/164")
        check("the end arrangement passes both join gates", end_rep["pass"] is True, str(end_rep))
        raises("an unknown blend_at is refused",
               lambda: lf.finish(src, tmp / "no.mp4", length=6.0, crossfade=0.5, blend_at="middle"),
               want="blend_at must be one of")

        print("the webm sibling")
        # Tiny (160x90) so the VP9 encode costs ~1 s. 4.0 s x 48 kHz = 192 000 samples, which is NOT a
        # whole number of 1024-sample AAC frames — so the mp4 must pad and the Opus sibling need not.
        small = tmp / "small.mp4"
        run(["ffmpeg", "-nostdin", "-v", "error", "-y",
             "-f", "lavfi", "-i", f"nullsrc=s=160x90:r={FPS}:d=6",
             "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=6",
             "-vf", "format=gray,geq=lum='mod(N,250)'", "-c:v", "libx264", "-crf", "26",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(small)])
        wr = lf.finish(small, tmp / "small_loop.mp4", length=4.0, crossfade=0.4, webm=True,
                       workdir=tmp / "work_webm")
        check("--webm emits a VP9/Opus sibling",
              wr["webm"] is not None and Path(wr["webm"]["output"]).is_file(), str(wr["webm"]))
        check("the sibling's padding is measured too, and is no worse than the mp4's",
              wr["webm"]["audio"]["codec_padding_samples"]
              <= wr["audio"]["codec_padding_samples"],
              f"webm {wr['webm']['audio']['codec_padding_ms']} ms vs "
              f"mp4 {wr['audio']['codec_padding_ms']} ms")

        print("refusals on real inputs")
        silent = tmp / "silent.mp4"
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"nullsrc=s=64x64:r={FPS}:d=8", "-c:v", "libx264", "-crf", "30",
             "-pix_fmt", "yuv420p", str(silent)])
        raises("refuses a source with no audio stream",
               lambda: lf.finish(silent, tmp / "no.mp4", length=4, crossfade=0.5),
               want="no audio stream")
        short = tmp / "short.flac"
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=220:sample_rate=44100:duration=3", str(short)])
        raises("refuses an --audio override too short for the wrap",
               lambda: lf.finish(src, tmp / "no.mp4", length=6, crossfade=0.5, audio=short),
               want="but the wrap needs")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
