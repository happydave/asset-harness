#!/usr/bin/env python3
"""Post-hoc lyric alignment: Demucs vocal stem -> WhisperX -> reconcile against the KNOWN lyrics.

The model-independent route. It works on any song — including one brought from outside this
pipeline — and it keeps working when ACE-Step is replaced, which is why it exists alongside the
model-native route (WI 1003).

Three steps, and the third is the one that matters:

  1. SEPARATE. Demucs (htdemucs) pulls the vocal stem out of the mix. This is not an optimisation:
     Whisper's lyric-transcription WER on a full mix vs a separated stem is 47.2% -> 27.7%
     (arXiv 2506.15514). Aligning against the mix is not a shortcut worth taking.

  2. RECOGNISE. WhisperX transcribes the stem and force-aligns it to word-level timings with a
     wav2vec2 model. Diarization is deliberately NOT used: the material is single-vocalist, and
     enabling it drags in pyannote (CC-BY-4.0 + HF-gated models) for no benefit.

  3. RECONCILE. We already know what was sung — the authored lyric sheet is an input, not something
     to rediscover. So the recognised word stream is sequence-matched against the known token
     stream, and each known LINE takes its timing from the recognised words that matched it. A line
     whose match is too thin is marked `low` confidence and interpolated, never silently guessed.

Known failure mode, expected and not tuned away: speech-trained aligners systematically mis-read
sung MELISMA (sustained/ornamented runs) as silence, because their acoustic models carry speech
phone-duration statistics and model no pitch. Line-level is therefore the honest granularity; word
timings inside a long held note are not to be trusted.

Runs on CPU by default — 75 seconds of audio does not need a GPU, and CPU-only torch sidesteps the
CUDA-version question entirely. Pass `--device cuda` if there is a reason to.

Environment: this script needs the track-local venv (`music-video/.venv`), NOT the system python.
    music-video/.venv/bin/python prototypes/align_posthoc.py ...
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import timeline as tlmod

WORD_RE = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens. Both streams get the same treatment so they are comparable."""
    return WORD_RE.findall(text.lower().replace("’", "'"))


def separate_vocals(audio: Path, work: Path, device: str) -> Path:
    """Demucs htdemucs -> vocals stem. Returns the stem path."""
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals",
           "-n", "htdemucs", "-d", device, "-o", str(work), str(audio)]
    print(f"  demucs: {' '.join(cmd[-6:])}")
    subprocess.run(cmd, check=True)
    stem = work / "htdemucs" / audio.stem / "vocals.wav"
    if not stem.exists():
        raise SystemExit(f"demucs produced no vocals stem at {stem}")
    return stem


def transcribe(stem: Path, device: str, model_name: str, compute_type: str) -> list[dict]:
    """WhisperX transcribe + word-level align on the stem. Returns word dicts with start/end."""
    import whisperx

    audio = whisperx.load_audio(str(stem))
    model = whisperx.load_model(model_name, device, compute_type=compute_type, language="en")
    result = model.transcribe(audio, batch_size=8)

    align_model, meta = whisperx.load_align_model(language_code="en", device=device)
    aligned = whisperx.align(result["segments"], align_model, meta, audio, device,
                             return_char_alignments=False)

    words: list[dict] = []
    for seg in aligned.get("segments", []):
        for w in seg.get("words", []):
            # wav2vec2 drops timings for tokens it cannot place — a word with no start is
            # exactly the melisma/silence case, and it must not be treated as time zero.
            if w.get("start") is None or w.get("end") is None:
                continue
            tok = normalize(w.get("word", ""))
            if tok:
                words.append({"token": tok[0], "start": float(w["start"]), "end": float(w["end"])})
    return words


def reconcile(entries: list[tuple[str, str]], words: list[dict], duration: float,
              min_match: float) -> list[tlmod.Line]:
    """Map recognised words onto the KNOWN lines by sequence alignment.

    The recognised stream and the authored stream are both flattened to token lists; difflib finds
    the matching blocks; each authored token inherits the time of the recognised token it matched.
    A line's span is then the first and last matched token within it.

    This is why alignment-of-known-text beats blind transcription: a mis-heard word costs one token
    out of a line, not a wrong lyric in the output.
    """
    known_tokens: list[str] = []
    owner: list[int] = []            # known_tokens[i] belongs to line owner[i]
    for li, (_section, text) in enumerate(entries):
        for tok in normalize(text):
            known_tokens.append(tok)
            owner.append(li)

    heard = [w["token"] for w in words]
    matcher = difflib.SequenceMatcher(a=heard, b=known_tokens, autojunk=False)

    # time[j] = timing of known token j, where matched
    times: dict[int, tuple[float, float]] = {}
    for i, j, n in matcher.get_matching_blocks():
        for k in range(n):
            times[j + k] = (words[i + k]["start"], words[i + k]["end"])

    per_line: dict[int, list[tuple[float, float]]] = {}
    counts: dict[int, int] = {}
    for j, li in enumerate(owner):
        counts[li] = counts.get(li, 0) + 1
        if j in times:
            per_line.setdefault(li, []).append(times[j])

    lines: list[tlmod.Line] = []
    for li, (section, text) in enumerate(entries):
        hits = per_line.get(li, [])
        ratio = len(hits) / max(1, counts.get(li, 1))
        if hits and ratio >= min_match:
            start, end = min(h[0] for h in hits), max(h[1] for h in hits)
            conf = "high"
        else:
            start = end = None            # filled by interpolation below
            conf = "low"
        lines.append(tlmod.Line(index=li, section=section, text=text,
                                start=start if start is not None else -1.0,
                                end=end if end is not None else -1.0,
                                confidence=conf))

    _interpolate_unmatched(lines, duration)
    _enforce_monotonic(lines, duration)
    return lines


def _interpolate_unmatched(lines: list[tlmod.Line], duration: float) -> None:
    """Give unmatched lines a placeholder span between their nearest matched neighbours.

    A line that could not be matched is still a line that was sung — dropping it would produce a
    timeline that is silently missing content, which is worse than one that is visibly uncertain.
    It keeps `confidence == "low"` so nothing downstream mistakes it for a measurement.
    """
    n = len(lines)
    for i, ln in enumerate(lines):
        if ln.start >= 0:
            continue
        prev_end = next((lines[k].end for k in range(i - 1, -1, -1) if lines[k].start >= 0), 0.0)
        nxt_start = next((lines[k].start for k in range(i + 1, n) if lines[k].start >= 0), duration)
        gap = max(0.0, nxt_start - prev_end)
        run = [k for k in range(i, n) if lines[k].start < 0]
        run = run[:1] + [k for k in run[1:] if k == run[run.index(k) - 1] + 1]
        share = gap / (len(run) + 1) if run else gap
        pos = run.index(i) if i in run else 0
        ln.start = round(prev_end + share * pos, 3)
        ln.end = round(min(duration, ln.start + max(share, 0.5)), 3)


def _enforce_monotonic(lines: list[tlmod.Line], duration: float) -> None:
    """Lyrics are sung in order; a timeline that says otherwise is wrong, not interesting.

    Clamps rather than discards, so a single bad word timing degrades one line instead of
    invalidating the run — and the affected lines are already marked or become visibly short.
    """
    floor = 0.0
    for ln in lines:
        ln.start = round(max(ln.start, floor), 3)
        ln.end = round(min(max(ln.end, ln.start + 0.2), duration), 3)
        floor = ln.start
    for i in range(len(lines) - 1):
        if lines[i].end > lines[i + 1].start:
            lines[i].end = round(max(lines[i].start + 0.2, lines[i + 1].start), 3)
    lines[-1].end = round(min(duration, max(lines[-1].end, lines[-1].start + 0.2)), 3)


def probe_duration(audio: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(audio)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--audio", required=True)
    ap.add_argument("--lyrics", required=True, help="the authored sheet — an INPUT, never re-derived")
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None, help="scratch dir for stems")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--model", default="small.en", help="faster-whisper model for the ASR pass")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--min-match", type=float, default=0.34,
                    help="fraction of a line's tokens that must match for `high` confidence")
    ap.add_argument("--skip-separation", action="store_true",
                    help="align against the raw mix — the labelled CONTROL, not a shortcut")
    args = ap.parse_args()

    audio = Path(args.audio)
    entries = tlmod.parse_lyric_sheet(Path(args.lyrics).read_text())
    duration = probe_duration(audio)
    work = Path(args.work) if args.work else here / "outputs" / "work"

    t0 = time.time()
    if args.skip_separation:
        stem, route_note = audio, "raw mix (control — no source separation)"
    else:
        stem = separate_vocals(audio, work, args.device)
        route_note = "demucs htdemucs vocal stem"
    t_sep = time.time() - t0

    t1 = time.time()
    words = transcribe(stem, args.device, args.model, args.compute_type)
    t_asr = time.time() - t1

    lines = reconcile(entries, words, duration, args.min_match)
    n_low = sum(1 for l in lines if l.confidence == "low")

    tl = tlmod.Timeline(
        audio=audio.name, duration=round(duration, 3),
        route="demucs-whisperx" if not args.skip_separation else "whisperx-rawmix",
        lines=lines,
        notes=(f"{route_note}; whisper={args.model}; {len(words)} words recognised; "
               f"{len(lines) - n_low}/{len(lines)} lines matched >= {args.min_match:.0%} of tokens; "
               f"separation {t_sep:.0f}s, asr+align {t_asr:.0f}s"))

    stem_out = Path(args.out) if args.out else audio.with_suffix("").with_name(audio.stem + "_posthoc")
    j, l = tlmod.write(tl, stem_out)
    print(f"\n  wrote {j}\n  wrote {l}")
    print(f"  {len(words)} words recognised; {len(lines) - n_low} high / {n_low} low confidence")
    print(f"  separation {t_sep:.0f}s, asr+align {t_asr:.0f}s, total {time.time() - t0:.0f}s")
    if n_low:
        print("  LOW-CONFIDENCE lines (interpolated, review these):")
        for ln in lines:
            if ln.confidence == "low":
                print(f"    [{ln.start:6.2f}] {ln.text}")


if __name__ == "__main__":
    main()
