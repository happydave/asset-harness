#!/usr/bin/env python3
"""Standalone frame interpolation for Wan i2v clips — a WORKSTATION post-step, NOT a ComfyUI node.

Wan2.2 i2v outputs 16 fps, which reads steppy/framey. This raises the frame rate of a finished mp4 with
ffmpeg's motion-compensated interpolation (`minterpolate`, `mi_mode=mci`). It is a pure post-process:

  * fps can be retargeted (32/48/60) in seconds without regenerating the ~1 h clip;
  * it runs here on the workstation (ai2 has no ffmpeg and stays free for generation);
  * the raw Wan clip stays the shot artifact (WI 1004's manifest -> pure-renderer boundary).

If `minterpolate` shows motion-compensation artifacts (warping/ghosting on crowds or limbs), the upgrade
is RIFE (a learned interpolator, e.g. rife-ncnn-vulkan) — a flagged install, deliberately NOT done here.

  interpolate.py in.mp4 --fps 48 --out out.mp4
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def interpolate(src: Path, dst: Path, fps: int, mi_mode: str = "mci") -> None:
    """Raise `src` to `fps` fps into `dst`. mci = motion-compensated (best); blend/dup = cheap fallbacks."""
    if mi_mode == "mci":
        # aobmc (adaptive overlapped block MC) + bidirectional ME + variable-size block MC = the
        # highest-quality minterpolate configuration.
        vf = (f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
    else:
        vf = f"minterpolate=fps={fps}:mi_mode={mi_mode}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf,
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(dst)]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help="input mp4 (a Wan i2v clip)")
    ap.add_argument("--out", required=True, help="output mp4")
    ap.add_argument("--fps", type=int, default=48, help="target frame rate (default 48)")
    ap.add_argument("--mi-mode", default="mci", choices=["mci", "blend", "dup"],
                    help="mci=motion-compensated (best), blend/dup=cheap fallbacks")
    args = ap.parse_args()
    interpolate(Path(args.src), Path(args.out), args.fps, args.mi_mode)
    print(f"-> {args.out}  ({args.fps} fps, minterpolate={args.mi_mode})")


if __name__ == "__main__":
    main()
