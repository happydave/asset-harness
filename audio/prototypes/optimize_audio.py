#!/usr/bin/env python3
"""ffmpeg post step for the audio track: normalize, trim, (seamless) loop, encode.

The model emits raw FLAC/WAV; this turns it into game-ready assets. Mirrors the role
3d-static-props/blender_optimize.py plays for meshes.

Per file:
  - EBU R128 loudness-normalize (`loudnorm`, target LUFS per asset class).
  - One-shots: trim leading/trailing silence + a short fade-out (no clicks).
  - Loops (`--loop`): author a seamless loop by crossfading the tail back onto the head
    (length-preserving), so the file loops without a seam.
  - Encode to .ogg (libvorbis, for Phaser/web) AND a 48 kHz .wav (Bevy / lossless).

Runs locally (ffmpeg on the workstation); ai2 has no ffmpeg.
"""
import argparse
import json
import subprocess
from pathlib import Path

VORBIS_Q = "5"          # ~160 kbps VBR — fine for SFX
# Keep the model's native sample rate (this build emits 44.1 kHz); no pointless resampling.


def _probe(path: Path) -> tuple[float, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=sample_rate",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    j = json.loads(out.stdout)
    return float(j["format"]["duration"]), int(j["streams"][0]["sample_rate"])


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _encode(wav: Path, out_dir: Path, name: str) -> tuple[Path, Path]:
    ogg = out_dir / f"{name}.ogg"
    wav_out = out_dir / f"{name}.wav"
    _run(["-i", str(wav), "-c:a", "libvorbis", "-q:a", VORBIS_Q, str(ogg)])
    _run(["-i", str(wav), "-c:a", "pcm_s16le", str(wav_out)])
    return ogg, wav_out


def process(src: Path, out_dir: Path, *, loop: bool, lufs: float, cross: float, fade: float) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = src.stem
    _, sr = _probe(src)
    rate = ["-ar", str(sr)]            # loudnorm internally goes 192 kHz; pin back to source rate
    norm = out_dir / f".{name}.norm.wav"
    tmp = out_dir / f".{name}.tmp.wav"

    # Pass 1: loudness-normalize on its own. `loudnorm` is a dynamic filter and misbehaves inside
    # a complex asplit/concat graph, so it gets a dedicated pass.
    _run(["-i", str(src), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", *rate, str(norm)])
    d = _probe(norm)[0]

    if loop:
        c = min(cross, d / 3)          # keep the crossfade well within the clip
        # Overlap-add seamless loop of length (d-c): the clip's tail is faded onto its head, so the
        # loop's final sample (original ~[d-c]) flows into the head (which begins as that same tail
        # content) — no seam. main=[0,d-c], tail=[d-c,d].
        fc = (
            f"[0:a]asplit=2[m][t];"
            f"[m]atrim=0:{d - c:.4f},asetpts=PTS-STARTPTS[main];"
            f"[t]atrim={d - c:.4f}:{d:.4f},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st=0:d={c:.4f}:curve=qsin[tailf];"
            f"[main]asplit=2[mh][mr];"
            f"[mh]atrim=0:{c:.4f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={c:.4f}:curve=qsin[headf];"
            f"[mr]atrim={c:.4f}:{d - c:.4f},asetpts=N/SR/TB[rest];"
            # amix emits odd PTS that confuse concat; regenerate timestamps on both segments.
            f"[headf][tailf]amix=inputs=2:normalize=0,asetpts=N/SR/TB[bhead];"
            f"[bhead][rest]concat=n=2:v=0:a=1[out]"
        )
        _run(["-i", str(norm), "-filter_complex", fc, "-map", "[out]", *rate, str(tmp)])
    else:
        # one-shot: strip true silence both ends (-60 dB keeps the decay tail). Optional short
        # fade-out (fade=0 keeps the clip ending hot, e.g. an ignition that blends into a loop).
        af = ("silenceremove=start_periods=1:start_silence=0.05:start_threshold=-60dB:"
              "detection=peak,areverse,"
              "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-60dB:"
              "detection=peak,areverse")
        if fade > 0:
            af += f",afade=t=out:st={max(0.0, d - fade):.4f}:d={fade}"
        _run(["-i", str(norm), "-af", af, *rate, str(tmp)])

    ogg, wav_out = _encode(tmp, out_dir, name)
    norm.unlink(missing_ok=True)
    tmp.unlink(missing_ok=True)
    return ogg, wav_out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="input audio file, or a directory with --batch")
    ap.add_argument("--out", default=None, help="output dir (default: <src dir>/optimized)")
    ap.add_argument("--loop", action="store_true", help="author a seamless loop (ambient/beds)")
    ap.add_argument("--lufs", type=float, default=-16.0, help="target integrated loudness")
    ap.add_argument("--cross", type=float, default=0.25, help="loop crossfade seconds")
    ap.add_argument("--fade", type=float, default=0.03, help="one-shot fade-out seconds")
    ap.add_argument("--batch", action="store_true", help="treat src as a dir of .flac/.wav")
    args = ap.parse_args()

    src = Path(args.src)
    out_dir = Path(args.out) if args.out else (src if src.is_dir() else src.parent) / "optimized"
    files = sorted([*src.glob("*.flac"), *src.glob("*.wav")]) if args.batch else [src]
    for f in files:
        ogg, wav = process(f, out_dir, loop=args.loop, lufs=args.lufs, cross=args.cross, fade=args.fade)
        print(f"{f.name} -> {ogg.name}, {wav.name}")


if __name__ == "__main__":
    main()
