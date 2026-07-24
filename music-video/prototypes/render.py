#!/usr/bin/env python3
"""Render a shot-list manifest to the lobby-loop mp4 -- a PURE function of the manifest + assets.

No creative decisions live here: every timing, image, move, and cut comes from the manifest
(`manifest.py`). That is what makes a gate cheap (review the manifest, not a re-render), a single shot
regenerable (swap its asset, re-run this), and the run resumable.

Pipeline, all direct-subprocess ffmpeg on the workstation (ai2 has no ffmpeg; MoviePy and
GPL-ffmpeg-bundling wrappers are avoided by policy -- WI 1004 traps):

  1. each shot -> a 1280x720 segment at FPS:
       still/kenburns : pre-upscale the source (~6400px, the zoompan sub-pixel-jitter fix), then
                        zoompan a slow Ken-Burns move driven by the output frame index;
       video          : the clip, scaled and fit to the shot window (trim if long, hold last frame
                        if short).
     Every non-final segment is rendered `XFADE` seconds long so the crossfade has material; this makes
     each xfade start exactly on its lyric boundary and keeps the assembled video's total equal to the
     song duration (see _assemble).
  2. xfade-chain the segments, mux the ORIGINAL song audio, encode web mp4 (h264/yuv420p + aac,
     +faststart), trimmed to the audio length.

Stdlib + ffmpeg only.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import manifest as M

FPS = 30
XFADE = 0.5          # crossfade seconds
UPSCALE_W = 6400     # pre-upscale width for zoompan sub-pixel precision (WI 1004 trap)
ZMAX = 1.12          # Ken-Burns zoom extent


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


class RenderError(RuntimeError):
    """A rendered artifact does not match what the manifest asked for. Raised before the next stage so
    a silent short segment (WI 1004 B-1) fails loudly and located instead of collapsing the assembly."""


# Duration tolerance: a looped-image segment quantises to round(seg_dur*FPS) frames, so the measured
# duration can differ from the target by up to half a frame; encoding adds a little slack. Two frames
# is comfortably inside that noise yet far below any real short-segment bug (B-1 shortfalls were seconds,
# not frames).
DUR_TOL = 2.0 / FPS


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=nk=1:nw=1", str(path)], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def _probe_video_duration(path: Path) -> float:
    """The VIDEO STREAM's real length (packet count / FPS), NOT the container duration.

    The distinction is the whole point of the final guard: after muxing, `format=duration` reports the
    max over streams, so an audio-padded-but-short video (exactly the B-1 symptom -- a 12 s video in a
    75 s container) passes a container-duration check. Counting video packets sees the truncation."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True)
    return int(out.stdout.strip()) / FPS


def _assert_duration(path: Path, expected: float, what: str, *, tol: float = DUR_TOL,
                     video_stream: bool = False) -> None:
    """Raise RenderError if `path` is not `expected` seconds (within `tol`). `video_stream` measures the
    video stream length rather than the container -- use it for the muxed output."""
    actual = _probe_video_duration(path) if video_stream else _probe_duration(path)
    if abs(actual - expected) > tol:
        raise RenderError(
            f"{what}: expected {expected:.3f}s but got {actual:.3f}s "
            f"(diff {actual - expected:+.3f}s, tol {tol:.3f}s) -- {path}")


def _kenburns_vf(kb: dict, seg_dur: float) -> str:
    """Ken-Burns filter: pre-upscale, then zoompan a slow move over `seg_dur` at FPS.

    Motion is driven by `on` (output frame index) over N frames, which is the robust single-image
    zoompan pattern (d=1, one output frame per looped input frame; length capped by -t on the input).
    """
    n = max(1, round(seg_dur * FPS))
    zoom = kb.get("zoom", "in")
    pan = kb.get("pan", "c")
    if zoom == "in":
        z = f"min(1.0+{ZMAX - 1.0:.3f}*on/{n},{ZMAX})"
    elif zoom == "out":
        z = f"max({ZMAX}-{ZMAX - 1.0:.3f}*on/{n},1.0)"
    else:  # none -- still needs z>1 so a pan has room
        z = "1.08"
    # crop-window offsets against the upscaled iw/ih and current `zoom`
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if pan == "l":      # pan left->right start: begin left
        x, y = f"(iw-iw/zoom)*on/{n}", cy
    elif pan == "r":
        x, y = f"(iw-iw/zoom)*(1-on/{n})", cy
    elif pan == "u":
        x, y = cx, f"(ih-ih/zoom)*on/{n}"
    elif pan == "d":
        x, y = cx, f"(ih-ih/zoom)*(1-on/{n})"
    else:
        x, y = cx, cy
    return (f"scale={UPSCALE_W}:-2,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s=1280x720:fps={FPS},"
            f"setsar=1")


def _render_still_segment(asset: Path, kb: dict, seg_dur: float, out: Path) -> None:
    # `-framerate FPS` on the looped image is essential: without it the image demuxer defaults to
    # 25 fps, so `-t seg_dur` yields seg_dur*25 frames that -r FPS then retags to seg_dur*25/FPS
    # seconds -- segments come out ~0.83x short and the xfade offsets overrun them (collapses the
    # chain). Setting the input rate makes -t seg_dur produce exactly seg_dur*FPS frames.
    _run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-loop", "1",
          "-t", f"{seg_dur:.3f}", "-i", str(asset), "-vf", _kenburns_vf(kb, seg_dur), "-r", str(FPS),
          "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def _render_video_segment(asset: Path, seg_dur: float, out: Path) -> None:
    """Fit a clip to the shot window: hold the last frame if short, trim if long."""
    clip_len = _probe_duration(asset)
    pad = max(0.0, seg_dur - clip_len)
    vf = (f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
          f"tpad=stop_mode=clone:stop_duration={pad:.3f},setsar=1,fps={FPS}")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(asset), "-vf", vf,
          "-t", f"{seg_dur:.3f}", "-r", str(FPS),
          "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def _assemble(segments: list[Path], boundaries: list[float], audio: Path,
              total: float, out: Path) -> None:
    """xfade-chain the segments at their lyric boundaries, mux the song audio, encode web mp4.

    Non-final segments were rendered XFADE seconds long, so offset_i == boundary b_i and the total
    equals the song duration. The audio is the timing source of truth; -t trims to it exactly.
    """
    inputs: list[str] = []
    for seg in segments:
        inputs += ["-i", str(seg)]
    inputs += ["-i", str(audio)]
    audio_idx = len(segments)

    steps = []
    prev = "[0:v]"
    for i in range(1, len(segments)):
        label = f"[v{i}]"
        off = boundaries[i]  # cumulative duration before shot i == where this fade begins
        steps.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={off:.3f}{label}")
        prev = label
    filtergraph = ";".join(steps)
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
          "-filter_complex", filtergraph,
          "-map", prev, "-map", f"{audio_idx}:a",
          "-t", f"{total:.3f}",
          # crf 26: constant Ken-Burns motion on every shot makes each frame differ, so a lower crf
          # overruns the go:embed budget; 26 keeps a 75 s 720p loop well under ~8 MB at 720p quality.
          "-c:v", "libx264", "-crf", "26", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
          str(out)])


def render(man: M.Manifest, manifest_dir: Path, out: Path, workdir: Path) -> Path:
    """Render `man` to `out`. Segments go under `workdir`. Assets resolve against `manifest_dir`."""
    M.validate(man, manifest_dir=manifest_dir)
    workdir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    boundaries: list[float] = []
    cum = 0.0
    n = len(man.shots)
    for s in man.shots:
        boundaries.append(round(cum, 3))
        cum += s.duration
        # non-final segments carry an extra XFADE of material for the crossfade
        seg_dur = s.duration + (XFADE if s.index < n - 1 else 0.0)
        asset = (manifest_dir / s.asset).resolve()
        seg = workdir / f"seg{s.index:02d}.mp4"
        if s.kind == "video":
            _render_video_segment(asset, seg_dur, seg)
        else:
            _render_still_segment(asset, s.kb, seg_dur, seg)
        # Guard: a segment shorter than asked-for makes the xfade offsets overrun it and collapses the
        # whole chain (WI 1004 B-1). Catch it here, at its source, not three stages downstream.
        _assert_duration(seg, seg_dur, f"shot {s.index} segment ({s.kind})")
        segments.append(seg)
    _assemble(segments, boundaries, (manifest_dir / man.audio).resolve(), man.duration, out)
    # Guard: the muxed VIDEO STREAM must reach the song duration -- a container-duration check would be
    # fooled by an audio-padded-but-short video (the visible B-1 symptom).
    _assert_duration(out, man.duration, "assembled video stream", tol=3.0 / FPS, video_stream=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifest", help="path to the shot-list manifest JSON")
    ap.add_argument("--out", required=True, help="output mp4 path")
    ap.add_argument("--workdir", default=None, help="segment work dir (default: <out dir>/work)")
    args = ap.parse_args()
    man_path = Path(args.manifest).resolve()
    man = M.from_json(man_path.read_text())
    out = Path(args.out)
    workdir = Path(args.workdir) if args.workdir else out.parent / "work"
    render(man, man_path.parent, out, workdir)
    dur = _probe_duration(out)
    size_mb = out.stat().st_size / 1e6
    print(f"-> {out}  ({dur:.1f}s, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
