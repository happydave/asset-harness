#!/usr/bin/env python3
"""Wrap-crossfade a rendered cut into a seamless loop (WI 1159) — a WORKSTATION post-step.

A music video that plays continuously behind a lobby has to survive its own end-to-start join. A plain
trim does not: the last sample of the cut and the first sample are unrelated material, which is a click,
and the last frame and the first frame are unrelated pictures, which is a jump.

The wrap fixes both by construction rather than by cleanup. Given a source cut of duration D, a loop
length T and a crossfade x (T + x <= D):

    out[0, x)  = source[T, T+x) fading out under source[0, x) fading in
    out[x, T)  = source[x, T) unchanged

so the output is exactly T seconds and, played on repeat, runs `... src(T-d) -> src(T) ...` across the
join — adjacent source material, with nothing to click on. Verified frame-exactly on a grey-ramp source:
out[0] = src[T], out[x] = src[x], out[last] = src[T-1/fps] (see the work item's plan.md).

    python3 loop_finish.py cut.mp4 --length 56.616 --crossfade 0.75 --search 2.0 \
        --audio song.flac --out cut_loop.mp4

Prints a JSON report: the chosen length, the envelope match, both join gates, and the codec padding.
Exit status is non-zero if a gate fails. Stdlib + ffmpeg only.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chain_clip as cc

# --- video join ------------------------------------------------------------------------------------
# Reused unchanged from WI 1160 so the two seam gates in this repo agree: a boundary passes when its
# SSIM is no worse than the local adjacent-frame mean by more than the tolerance.
SEAM_TOLERANCE = cc.SEAM_TOLERANCE      # 0.05
SEAM_WINDOW = cc.SEAM_WINDOW            # 8 frames

# --- audio join ------------------------------------------------------------------------------------
# A click is, by definition, the largest jump in its neighbourhood: the join's sample-to-sample step is
# compared against the biggest step already present within LOCAL_MS either side of it.
LOCAL_MS = 50.0

# ...with a factor of headroom, because the two sides of the join do NOT share quantisation noise. Every
# other adjacent pair sits inside one codec frame; the join pairs the last sample of the cut with the
# first, which the encoder coded independently. Measured on a wrapped synthetic whose join is exact by
# construction: join step 96 against a local maximum of 86 — a 1.12x ratio from coding noise alone. A
# real discontinuity is not a near miss: a mid-cycle trim of the same source scores ~30x. The reported
# ratio is what to look at; the bound only has to separate those two populations.
DISCONTINUITY_TOLERANCE = 2.0

# Level continuity across the dissolve, measured on PURE material either side of it (a window that
# overlaps the crossfade measures the crossfade, not the music). Now calibrated rather than invented:
# the owner-accepted lobby loop steps 4.4x (~13 dB) — a crossfade bridges a step, it cannot remove one —
# while a plain trim of the same kind of material measures 100x+. 8x sits between them with margin on
# both sides. The measured ratio is always reported; the bound only has to separate those populations.
LEVEL_MS = 100.0
LEVEL_TOLERANCE = 8.0                   # factor, i.e. ~18 dB

# --- loop-point search -----------------------------------------------------------------------------
# The search matches a short-time RMS envelope, so it aligns rhythm and dynamics — bar phase — and is
# blind to harmony. That limit is why the owner listen remains the last gate.
ENVELOPE_RATE = 8000                    # Hz, mono, for envelope analysis only
ENVELOPE_HOP = 0.010                    # seconds per envelope frame
MATCH_MIN = 0.5                         # seconds of envelope compared, at least


# Where the wrap's dissolve sits in the file. The two arrangements are rotations of one cycle and loop
# identically; `end` opens a single pass on clean material instead of mid-dissolve (WI 1181).
BLEND_AT = ("end", "start")


class LoopError(RuntimeError):
    """A loop cannot be built as asked, or a built loop fails a join gate."""


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise LoopError(f"{cmd[0]} failed: {r.stderr.strip()[:400]}")
    return r.stdout


def probe_fps(path: Path) -> float:
    """Frames per second as a float, from the r_frame_rate rational."""
    rate = cc.probe(path)["fps"]
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1)


def probe_duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nk=1:nw=1", str(path)])
    return float(out.strip())


def has_audio(path: Path) -> bool:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=index", "-of", "csv=p=0", str(path)])
    return bool(out.strip())


def audio_rate(path: Path) -> int:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=sample_rate", "-of", "csv=p=0", str(path)])
    return int(out.strip())


def decode_mono(path: Path, dst: Path, rate: int | None = None) -> array.array:
    """Decode `path`'s audio to a mono WAV at `rate` (native when None) and read the samples."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-map", "0:a", "-ac", "1"]
    if rate:
        cmd += ["-ar", str(rate)]
    cmd += ["-c:a", "pcm_s16le", str(dst)]
    _run(cmd)
    with wave.open(str(dst)) as w:
        samples = array.array("h")
        samples.frombytes(w.readframes(w.getnframes()))
    return samples


def rms(samples, lo: int = 0, hi: int | None = None) -> float:
    hi = len(samples) if hi is None else hi
    n = max(1, hi - lo)
    return math.sqrt(sum(v * v for v in samples[lo:hi]) / n)


def envelope(samples: array.array, rate: int, hop: float = ENVELOPE_HOP) -> list[float]:
    """Short-time RMS, one value per `hop` seconds."""
    step = max(1, int(round(rate * hop)))
    return [rms(samples, i, min(i + step, len(samples))) for i in range(0, len(samples), step)]


def envelope_distance(env: list[float], at: int, width: int) -> float:
    """Normalised L1 distance between the envelope's head window and the window starting at `at`.

    0 = the material at `at` has the same rhythmic shape as the material the loop returns to; 1 = no
    resemblance. Normalised so a loud passage is not penalised for being loud.
    """
    head = env[:width]
    tail = env[at:at + width]
    if len(tail) < width:
        raise LoopError(f"envelope too short: need {at + width} frames, have {len(env)}")
    total = sum(head) + sum(tail)
    if total <= 0:
        return 0.0
    return sum(abs(a - b) for a, b in zip(head, tail)) / total


def choose_length(env: list[float], length: float, crossfade: float, search: float,
                  fps: float, hop: float = ENVELOPE_HOP) -> dict:
    """Pick the loop length: the best-matching whole-frame candidate in [length-search, length].

    Backwards-only by design. The authored length is a boundary the author chose — a section start, a
    lyric onset — so moving EARLIER only trims material before that boundary, while moving LATER would
    cut into the phrase that begins there. `search = 0` uses the authored length unchanged.
    """
    width = max(1, int(round(max(crossfade, MATCH_MIN) / hop)))
    hi_frame = int(round(length * fps))
    lo_frame = int(round((length - search) * fps))
    scored = []
    for n in range(lo_frame, hi_frame + 1):
        t = n / fps
        scored.append((envelope_distance(env, int(round(t / hop)), width), n, t))
    scored.sort(key=lambda s: (s[0], -s[1]))     # best match; ties resolve to the longer cut
    dist, frames, chosen = scored[0]
    authored = envelope_distance(env, int(round(hi_frame / fps / hop)), width)
    return {"length": round(chosen, 4), "frames": frames, "candidates": len(scored),
            "envelope_distance": round(dist, 4), "authored_distance": round(authored, 4),
            "match_window_s": round(width * hop, 3)}


def check_params(duration: float, length: float, crossfade: float, search: float) -> None:
    """Refuse an impossible loop before anything is encoded."""
    if length <= 0:
        raise LoopError(f"length must be positive, got {length}")
    if crossfade <= 0:
        raise LoopError(f"crossfade must be positive, got {crossfade}")
    if search < 0:
        raise LoopError(f"search must not be negative, got {search}")
    if search >= length:
        raise LoopError(f"search {search}s >= length {length}s: the window runs past the start")
    if crossfade >= length - search:
        raise LoopError(f"crossfade {crossfade}s is not shorter than the shortest candidate "
                        f"{length - search}s")
    if length + crossfade > duration + 1e-6:
        raise LoopError(f"source is {duration:.3f}s but the wrap needs {length + crossfade:.3f}s "
                        f"(length {length} + crossfade {crossfade})")


MP4_ARGS = ["-c:v", "libx264", "-crf", "26", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
# VP9/Opus: the container that can actually be sample-gapless, for the case where mp4's ~8 ms of AAC
# padding is audible at the join. Opt-in (--webm) — it is a slow encode and the delivered artifact is
# the mp4.
WEBM_ARGS = ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-cpu-used", "4",
             "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", "128k"]


def wrap(src: Path, out: Path, length: float, crossfade: float, *, audio: Path | None = None,
         curve: str = "tri", encoder: list[str] | None = None, blend_at: str = "end",
         fps: float | None = None) -> Path:
    """Write the T-second loop cut. `blend_at` says where in the file the dissolve sits.

    Both arrangements are the SAME CYCLE — one is a rotation of the other by `crossfade` — so they loop
    identically. What differs is a single pass:

      start : out = [blend(src[T,T+x) over src[0,x))] + src[x,T)
              The file opens mid-dissolve, on material from the end of the cut that a first-time viewer
              has not seen yet.
      end   : out = src[x,T) + [blend(src[T,T+x) over src[0,x))]
              The file opens on clean material `x` into the cut and ends by dissolving back toward its
              own opening. Default, because it is better on a single pass and identical on repeat.

    The discretisation matters and is why `end` does not simply reuse `xfade`: a crossfade's weights run
    0 -> (N-1)/N, so its FIRST frame is pure outgoing and its LAST frame still carries 1/N of it. Under
    `start` that impure frame sits harmlessly inside the file; a naive rotation would park it on the
    file's final frame — exactly where the loop join is measured and seen. `end` therefore blends with
    explicit weights running 1/N -> 1, which puts the exact frame at the boundary and the impure one at
    the start of the dissolve, where a 1/N ghost is invisible.
    """
    if blend_at not in BLEND_AT:
        raise LoopError(f"blend_at must be one of {BLEND_AT}, got {blend_at!r}")
    fps = fps or probe_fps(src)
    n = max(1, int(round(crossfade * fps)))      # blend frames
    xf = n / fps                                 # crossfade quantised to whole frames
    # Work in whole frames throughout: a length rounded to a few decimals (55.8667 for 1676/30)
    # lands a hair past the frame grid, and ffmpeg's -t then admits one more frame per cut. The
    # lobby's 56.0 s sat exactly on the grid, which is why this only surfaced on a searched length.
    total = int(round(length * fps))
    length = total / fps
    asrc = audio or src
    out.parent.mkdir(parents=True, exist_ok=True)

    if blend_at == "start":
        inputs = ["-ss", f"{length:.6f}", "-t", f"{xf:.6f}", "-i", str(src),
                  "-ss", "0", "-t", f"{length:.6f}", "-i", str(src)]
        av, ah = "[0:a]", "[1:a]"
        if audio is not None:
            inputs += ["-ss", f"{length:.6f}", "-t", f"{xf:.6f}", "-i", str(asrc),
                       "-ss", "0", "-t", f"{length:.6f}", "-i", str(asrc)]
            av, ah = "[2:a]", "[3:a]"
        graph = (f"[0:v][1:v]xfade=transition=fade:duration={xf:.6f}:offset=0[v];"
                 f"{av}{ah}acrossfade=d={xf:.6f}:c1={curve}:c2={curve}[a]")
    else:
        mid = (total - n) / fps
        inputs = ["-ss", f"{xf:.6f}", "-t", f"{mid:.6f}", "-i", str(src),        # 0 mid
                  "-ss", f"{length:.6f}", "-t", f"{xf:.6f}", "-i", str(src),     # 1 tail
                  "-ss", "0", "-t", f"{xf:.6f}", "-i", str(src)]                 # 2 head start
        am, av, ah = "[0:a]", "[1:a]", "[2:a]"
        if audio is not None:
            inputs += ["-ss", f"{xf:.6f}", "-t", f"{mid:.6f}", "-i", str(asrc),
                       "-ss", f"{length:.6f}", "-t", f"{xf:.6f}", "-i", str(asrc),
                       "-ss", "0", "-t", f"{xf:.6f}", "-i", str(asrc)]
            am, av, ah = "[3:a]", "[4:a]", "[5:a]"
        # Weights N/n. `blend`'s N counts from 1 (measured), so the first blend frame carries 1/n of the
        # incoming material and the LAST one is exactly it -- see the docstring for why that matters.
        expr = f"A*(1-min(1\\,N/{n}))+B*min(1\\,N/{n})"
        graph = (f"[1:v][2:v]blend=all_expr='{expr}'[b];"
                 f"[0:v][b]concat=n=2:v=1:a=0[v];"
                 f"{av}{ah}acrossfade=d={xf:.6f}:c1={curve}:c2={curve}[ba];"
                 f"{am}[ba]concat=n=2:v=0:a=1[a]")

    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", graph,
          "-map", "[v]", "-map", "[a]", *(encoder or MP4_ARGS), str(out)])
    return out


def keyframe_boundaries(clip: Path, limit: int = 3) -> list[int]:
    """Frame indices of interior keyframes — the boundaries a fair comparison for frame 0 must use."""
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(clip)])
    times = [float(t.rstrip(",")) for t in out.split() if t.strip(",")]
    fps = probe_fps(clip)
    frames = cc.probe(clip)["frames"]
    idx = [int(round(t * fps)) for t in times]
    return [i for i in idx if 1 <= i < frames - 1][:limit]


def video_join(out: Path, workdir: Path) -> dict:
    """SSIM across the loop join (last frame -> first frame), against two norms.

    The **local** norm is the adjacent-frame mean over the frames preceding the join — the WI 1160 gate,
    which measures content continuity. The **keyframe** norm exists because the join is not an ordinary
    adjacent pair: frame 0 is an IDR, coded independently, so its quantisation noise is uncorrelated
    with the P-frame chain the local norm is drawn from. Measured on the lobby cut, the same two source
    frames score 0.983 inside one encode and 0.945 across the loop's keyframe — the difference is coding
    noise, not motion. The keyframe norm compares like with like: the best interior keyframe boundary in
    this same file. A pass on either norm is a pass.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    frames_dir = workdir / "_joinframes"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    n = cc.probe(out)["frames"]
    # The last SEAM_WINDOW+1 frames establish the norm; frame 0 is the other side of the join.
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out),
          "-vf", f"select='gte(n\\,{n - SEAM_WINDOW - 1})'", "-fps_mode", "passthrough",
          str(frames_dir / "tail%03d.png")])
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out),
          "-vf", "select='eq(n\\,0)'", "-frames:v", "1", str(frames_dir / "first.png")])
    tail = sorted(frames_dir.glob("tail*.png"))
    if len(tail) < 2:
        raise LoopError(f"expected the last {SEAM_WINDOW + 1} frames, extracted {len(tail)}")
    window = [cc.ssim(tail[i], tail[i + 1]) for i in range(len(tail) - 1)]
    norm = sum(window) / len(window)
    join = cc.ssim(tail[-1], frames_dir / "first.png")

    kf_scores = []
    for j, k in enumerate(keyframe_boundaries(out)):
        before, after = frames_dir / f"kb{j}a.png", frames_dir / f"kb{j}b.png"
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out),
              "-vf", f"select='eq(n\\,{k - 1})'", "-frames:v", "1", str(before)])
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out),
              "-vf", f"select='eq(n\\,{k})'", "-frames:v", "1", str(after)])
        kf_scores.append(cc.ssim(before, after))
    # max, not mean: a keyframe that lands mid-dissolve measures the dissolve, not the coding cost.
    kf_norm = max(kf_scores) if kf_scores else None

    local_gap = norm - join
    kf_gap = (kf_norm - join) if kf_norm is not None else None
    return {"frames": n, "join_ssim": round(join, 4), "local_norm": round(norm, 4),
            "gap": round(local_gap, 4),
            "keyframe_norm": round(kf_norm, 4) if kf_norm is not None else None,
            "keyframe_gap": round(kf_gap, 4) if kf_gap is not None else None,
            "pass": local_gap <= SEAM_TOLERANCE
                    or (kf_gap is not None and kf_gap <= SEAM_TOLERANCE)}


def audio_join(out: Path, length: float, workdir: Path, *, crossfade: float = 0.0,
               blend_at: str = "end") -> dict:
    """Discontinuity and level continuity, plus the codec's own padding.

    Measured over the decoded stream TRUNCATED to the intended sample count. An mp4's decoded audio
    carries trailing codec padding — digital silence — so measuring to the decoded end would compare the
    first sample against a zero and report a large jump for every correctly-built loop.

    The two checks look at different places, on purpose:

    * **Discontinuity** at the file boundary, where a click would be — the last intended sample against
      the first.
    * **Level across the DISSOLVE**, using pure material on each side. Inside the dissolve the signal is
      a mixture of both ends, so a window that overlaps it measures the crossfade rather than the music:
      on the lobby cut that inflated the reported step by ~40 %. Where the dissolve sits depends on
      `blend_at`, so both are needed to place the windows. With `crossfade = 0` the windows collapse to
      the file boundary (the old behaviour), which is what a caller measuring a plain trim wants.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    rate = audio_rate(out)
    samples = decode_mono(out, workdir / "_join.wav")
    intended = int(round(length * rate))
    padding = len(samples) - intended
    if intended < 2 or len(samples) < intended:
        raise LoopError(f"decoded {len(samples)} samples, expected at least {intended}")

    join_delta = abs(samples[0] - samples[intended - 1])
    w = int(round(LOCAL_MS / 1000.0 * rate))
    local = max(
        max((abs(samples[i + 1] - samples[i]) for i in range(intended - 1 - w, intended - 1)),
            default=0),
        max((abs(samples[i + 1] - samples[i]) for i in range(0, w)), default=0))

    lw = int(round(LEVEL_MS / 1000.0 * rate))
    xs = int(round(crossfade * rate))
    if xs and blend_at == "end":          # dissolve occupies the last `crossfade` of the file
        before = rms(samples, max(0, intended - xs - lw), intended - xs)
        after = rms(samples, 0, lw)
    elif xs:                              # `start`: dissolve occupies the first `crossfade`
        before = rms(samples, intended - lw, intended)
        after = rms(samples, xs, xs + lw)
    else:
        before = rms(samples, intended - lw, intended)
        after = rms(samples, 0, lw)
    ratio = (max(before, after) + 1e-9) / (min(before, after) + 1e-9)
    disc_ratio = join_delta / (local + 1e-9)
    return {"sample_rate": rate, "intended_samples": intended,
            "codec_padding_samples": padding, "codec_padding_ms": round(1000 * padding / rate, 2),
            "join_delta": join_delta, "local_max_delta": local,
            "discontinuity_ratio": round(disc_ratio, 2),
            "discontinuity_pass": disc_ratio <= DISCONTINUITY_TOLERANCE,
            "rms_before": round(before, 1), "rms_after": round(after, 1),
            "level_window": "either side of the dissolve" if xs else "either side of the join",
            "level_ratio": round(ratio, 3), "level_pass": ratio <= LEVEL_TOLERANCE}


def finish(src: Path, out: Path, *, length: float, crossfade: float, search: float = 0.0,
           audio: Path | None = None, curve: str = "tri", webm: bool = False,
           blend_at: str = "end", workdir: Path | None = None) -> dict:
    """Choose the loop length, build the wrap, and measure both joins. Returns the report."""
    if blend_at not in BLEND_AT:
        raise LoopError(f"blend_at must be one of {BLEND_AT}, got {blend_at!r}")
    if not has_audio(src):
        raise LoopError(f"{src} has no audio stream; the wrap is defined on both streams")
    duration = probe_duration(src)
    check_params(duration, length, crossfade, search)
    if audio is not None:
        adur = probe_duration(audio)
        if adur + 1e-6 < length + crossfade:
            raise LoopError(f"--audio {audio} is {adur:.3f}s but the wrap needs "
                            f"{length + crossfade:.3f}s")

    fps = probe_fps(src)
    work = workdir or out.parent / f"{out.stem}_loopwork"
    work.mkdir(parents=True, exist_ok=True)

    if search > 0:
        env_samples = decode_mono(audio or src, work / "_env.wav", ENVELOPE_RATE)
        chosen = choose_length(envelope(env_samples, ENVELOPE_RATE), length, crossfade, search, fps)
    else:
        frames = int(round(length * fps))
        chosen = {"length": round(frames / fps, 4), "frames": frames, "candidates": 1,
                  "envelope_distance": None, "authored_distance": None, "match_window_s": None}
    t = chosen["frames"] / fps  # the exact grid length; chosen["length"] is its 4-decimal display

    wrap(src, out, t, crossfade, audio=audio, curve=curve, blend_at=blend_at, fps=fps)
    report = {"output": str(out), "source": str(src), "source_duration": round(duration, 3),
              "requested_length": length, "search": search, "crossfade": crossfade, "curve": curve,
              "blend_at": blend_at, "fps": fps, "chosen": chosen,
              "video": video_join(out, work),
              "audio": audio_join(out, t, work, crossfade=crossfade, blend_at=blend_at),
              "webm": None}
    # The wrap must produce exactly the loop length in frames. A concat of two trimmed pieces (the
    # `end` arrangement) is where an off-by-one would appear, so check rather than assume.
    if report["video"]["frames"] != chosen["frames"]:
        raise LoopError(f"loop cut has {report['video']['frames']} frames, expected "
                        f"{chosen['frames']} ({t}s at {fps} fps)")
    if webm:
        alt = out.with_suffix(".webm")
        wrap(src, alt, t, crossfade, audio=audio, curve=curve, encoder=WEBM_ARGS,
             blend_at=blend_at, fps=fps)
        report["webm"] = {"output": str(alt),
                          "audio": audio_join(alt, t, work, crossfade=crossfade,
                                              blend_at=blend_at)}
    v, a = report["video"], report["audio"]
    report["pass"] = bool(v["pass"] and a["discontinuity_pass"] and a["level_pass"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path, help="the rendered cut to loop (video + audio)")
    ap.add_argument("--length", type=float, required=True, help="loop length in seconds (authored)")
    ap.add_argument("--crossfade", type=float, default=0.75, help="wrap crossfade seconds")
    ap.add_argument("--search", type=float, default=0.0,
                    help="search this many seconds BACKWARDS from --length for a better loop point "
                         "(0 = use the authored length exactly)")
    ap.add_argument("--audio", type=Path, default=None,
                    help="take the audio from this file instead of the source's own track "
                         "(the original song, to avoid a second lossy generation)")
    ap.add_argument("--out", type=Path, default=None, help="output mp4 (default: <src>_loop.mp4)")
    ap.add_argument("--curve", default="tri", choices=["tri", "qsin", "esin", "hsin", "log", "par"],
                    help="fade curve; tri (linear) suits the similar material the search selects")
    ap.add_argument("--blend-at", default="end", choices=list(BLEND_AT),
                    help="where the wrap's dissolve sits: end (default -- a single pass opens clean) "
                         "or start. The two are rotations of one cycle and loop identically")
    ap.add_argument("--webm", action="store_true",
                    help="also emit a VP9/Opus sibling — the container that can be sample-gapless, "
                         "for the case where mp4's ~8 ms of AAC padding is audible")
    ap.add_argument("--workdir", type=Path, default=None)
    a = ap.parse_args()

    out = a.out or a.src.with_name(f"{a.src.stem}_loop.mp4")
    report = finish(a.src, out, length=a.length, crossfade=a.crossfade, search=a.search,
                    audio=a.audio, curve=a.curve, webm=a.webm, blend_at=a.blend_at,
                    workdir=a.workdir)
    out.with_suffix(".loop.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        v, au = report["video"], report["audio"]
        why = []
        if not v["pass"]:
            why.append(f"video join SSIM {v['join_ssim']} vs local norm {v['local_norm']} "
                       f"(gap {v['gap']}) and keyframe norm {v['keyframe_norm']} "
                       f"(gap {v['keyframe_gap']}), limit {SEAM_TOLERANCE}")
        if not au["discontinuity_pass"]:
            why.append(f"audio step {au['join_delta']} is {au['discontinuity_ratio']}x the local "
                       f"maximum {au['local_max_delta']} (limit {DISCONTINUITY_TOLERANCE}x)")
        if not au["level_pass"]:
            why.append(f"level ratio {au['level_ratio']} across the join exceeds "
                       f"{LEVEL_TOLERANCE}")
        print("\nLOOP GATE FAILED: " + "; ".join(why), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
