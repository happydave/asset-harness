#!/usr/bin/env python3
"""Tap along to the song to produce a lyric timeline. The floor beneath every automated route.

Play the audio, press ENTER as each lyric line *starts* being sung, and this writes the same
timeline format the automated routes emit. About 16 taps for a 75-second song.

This is not a consolation prize. A human is already in the loop at the candidate-pick gate — they
have to listen to the candidates anyway — so tapping through the winner once is a plausible
*permanent* answer, not merely a fallback. It also has the property no aligner has: it cannot be
defeated by melisma, by a mumbled consonant, or by a model that sings the wrong words, because the
person tapping is hearing what actually happened.

Requires only the standard library plus `ffplay`/`ffprobe` (both part of ffmpeg, already required by
the audio track's post-processing).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import timeline as tlmod


def probe_duration(audio: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def collect_taps(entries: list[tuple[str, str]], audio: Path, countdown: float) -> list[float] | None:
    """Play the audio and record one tap per line. Returns None if the take was abandoned.

    The clock starts when ffplay starts, after a fixed countdown so the operator is not scrambling
    for the first line. Timing is measured against `time.monotonic()`, not against ffplay's own
    position, because we only need *relative* accuracy and monotonic time is not subject to the
    player's buffering.
    """
    print(f"\n{len(entries)} lines to tap. ENTER = this line starts now.  q + ENTER = abandon take.\n")
    for i in range(int(countdown), 0, -1):
        print(f"  starting in {i}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 30, end="\r")

    player = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio)])
    t0 = time.monotonic()
    taps: list[float] = []
    try:
        for i, (section, text) in enumerate(entries):
            nxt = entries[i + 1][1] if i + 1 < len(entries) else "(end)"
            print(f"  [{i + 1:2d}/{len(entries)}] ({section}) {text}\n       next: {nxt}")
            if sys.stdin.readline().strip().lower() == "q":
                print("\n  take abandoned — nothing written.")
                return None
            taps.append(time.monotonic() - t0)
    finally:
        player.terminate()
        try:
            player.wait(timeout=5)
        except subprocess.TimeoutExpired:
            player.kill()
    return taps


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--audio", required=True, help="the song to tap along to")
    ap.add_argument("--lyrics", required=True, help="the authored lyric sheet (input, never re-derived)")
    ap.add_argument("--out", default=None, help="output stem (default: alongside the audio)")
    ap.add_argument("--countdown", type=float, default=3, help="seconds before playback starts")
    ap.add_argument("--taps", default=None,
                    help="JSON list of tap times — skip the interactive loop (for testing/replay)")
    args = ap.parse_args()

    audio = Path(args.audio)
    entries = tlmod.parse_lyric_sheet(Path(args.lyrics).read_text())
    if not entries:
        raise SystemExit(f"no lyric lines found in {args.lyrics}")
    duration = probe_duration(audio)

    if args.taps:
        taps = json.loads(Path(args.taps).read_text() if Path(args.taps).exists() else args.taps)
        notes = "replayed from recorded taps"
    else:
        taps = collect_taps(entries, audio, args.countdown)
        if taps is None:
            return
        notes = "tapped live by the operator"

    tl = tlmod.taps_to_timeline(entries, taps, duration, audio=audio.name, notes=notes)
    stem = Path(args.out) if args.out else audio.with_suffix("")
    j, l = tlmod.write(tl, stem)
    print(f"\n  wrote {j}\n  wrote {l}")
    print(f"  {len(tl.lines)} lines, {tl.lines[0].start:.2f}s .. {tl.lines[-1].end:.2f}s")
    print("  check it: play the audio with the .lrc loaded and watch whether the words land.")


if __name__ == "__main__":
    main()
