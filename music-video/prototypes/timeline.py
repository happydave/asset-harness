#!/usr/bin/env python3
"""The lyric timeline: the `music-video` track's join between a song and its shots.

Everything downstream of the chosen song — which image belongs to which lyric, where the cuts fall,
the whole edit — is a function of *when each lyric line is sung*. This module defines the one format
that carries that, so the shot-list manifest cannot tell which route produced its timings:

  * owner-tap        (tap_align.py)      -- the floor; always works
  * demucs-whisperx  (align_posthoc.py)  -- post-hoc, model-independent
  * acestep-native   (WI 1003)           -- model-native, from ACE-Step's own cross-attention

Line-level is the target. Word-level is a bonus nothing here needs: there is no lip sync in scope,
and speech-trained aligners are documented to mis-read sung melisma as silence, so sub-line precision
on singing is not trustworthy anyway.

Pure stdlib, and deliberately free of any interactive or model code so it can be tested without a
human at a keyboard or a GPU in the loop.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SECTION_RE = re.compile(r"^\s*\[([a-zA-Z][a-zA-Z0-9 _-]*)\]\s*$")

# How confident we are in a line's timing.
#   owner -- a human tapped it; authoritative by definition
#   high  -- an automated route matched this line unambiguously
#   low   -- an automated route could not match it confidently; NEEDS REVIEW, never silently trusted
CONFIDENCES = ("owner", "high", "low")


@dataclass
class Line:
    index: int
    section: str
    text: str
    start: float
    end: float
    confidence: str = "owner"

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Timeline:
    audio: str
    duration: float
    route: str
    lines: list[Line] = field(default_factory=list)
    notes: str = ""


class TimelineError(ValueError):
    """A timeline is malformed. Raised at emit time so a bad timeline never reaches disk."""


def parse_lyric_sheet(text: str) -> list[tuple[str, str]]:
    """Split an authored lyric sheet into (section, line) pairs.

    Structural tags ([verse], [chorus], ...) are the join key between a lyric line and a shot, and
    they survive even when precise timestamps do not — so they are carried through, not discarded.
    Blank lines separate stanzas visually and carry no timing.
    """
    out: list[tuple[str, str]] = []
    section = "unknown"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1).strip().lower()
            continue
        out.append((section, line))
    return out


def taps_to_timeline(entries: list[tuple[str, str]], taps: list[float], duration: float,
                     audio: str, route: str = "owner-tap", notes: str = "") -> Timeline:
    """Convert per-line tap times into spans.

    A tap marks a *boundary*, not a span: line i runs from its own tap to the next line's tap, and
    the last line runs to the end of the audio. That is the only sane reading of one keypress per
    line, and it is why a partially-tapped take is worthless — every line's end depends on the next
    line existing.
    """
    if len(taps) != len(entries):
        raise TimelineError(
            f"{len(taps)} taps for {len(entries)} lines — a partial take cannot be converted; re-run")
    lines = []
    for i, ((section, text), start) in enumerate(zip(entries, taps)):
        end = taps[i + 1] if i + 1 < len(taps) else duration
        lines.append(Line(index=i, section=section, text=text,
                          start=round(float(start), 3), end=round(float(end), 3),
                          confidence="owner"))
    tl = Timeline(audio=audio, duration=round(float(duration), 3), route=route, lines=lines, notes=notes)
    validate(tl)
    return tl


def validate(tl: Timeline) -> None:
    """Reject a malformed timeline rather than writing it.

    A downstream edit built on a silently-broken timeline is far more expensive to debug than a
    loud failure here.
    """
    if not tl.lines:
        raise TimelineError("timeline has no lines")
    if tl.duration <= 0:
        raise TimelineError(f"non-positive audio duration {tl.duration}")
    prev_start = -1.0
    for ln in tl.lines:
        if ln.confidence not in CONFIDENCES:
            raise TimelineError(f"line {ln.index}: unknown confidence {ln.confidence!r}")
        if not ln.text.strip():
            raise TimelineError(f"line {ln.index}: empty text")
        if ln.start < 0:
            raise TimelineError(f"line {ln.index}: negative start {ln.start}")
        if ln.end <= ln.start:
            raise TimelineError(f"line {ln.index}: end {ln.end} not after start {ln.start}")
        if ln.end > tl.duration + 1e-6:
            raise TimelineError(f"line {ln.index}: end {ln.end} beyond audio duration {tl.duration}")
        if ln.start < prev_start - 1e-6:
            raise TimelineError(f"line {ln.index}: start {ln.start} precedes previous line's start")
        prev_start = ln.start


def to_json(tl: Timeline) -> str:
    validate(tl)
    d = asdict(tl)
    return json.dumps(d, indent=2) + "\n"


def from_json(text: str) -> Timeline:
    d = json.loads(text)
    tl = Timeline(audio=d["audio"], duration=d["duration"], route=d["route"],
                  lines=[Line(**ln) for ln in d["lines"]], notes=d.get("notes", ""))
    validate(tl)
    return tl


def _lrc_stamp(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"[{int(m):02d}:{s:05.2f}]"


def to_lrc(tl: Timeline) -> str:
    """Standard LRC — the interchange format any media player can check by ear.

    Emitted alongside the JSON precisely so a timeline is verifiable without writing a tool: load the
    audio and the .lrc in a player and watch whether the words land.
    """
    validate(tl)
    head = [f"[re:asset-harness music-video ({tl.route})]", f"[length:{_lrc_stamp(tl.duration)[1:-1]}]"]
    body = [f"{_lrc_stamp(ln.start)}{ln.text}" for ln in tl.lines]
    return "\n".join(head + body) + "\n"


def write(tl: Timeline, stem: Path) -> tuple[Path, Path]:
    """Write both representations. JSON is what the shot list consumes; LRC is what a human checks."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    j, l = stem.with_suffix(".timeline.json"), stem.with_suffix(".lrc")
    j.write_text(to_json(tl))
    l.write_text(to_lrc(tl))
    return j, l
