#!/usr/bin/env python3
"""The shot-list manifest: the `music-video` track's durable artifact.

A song plus a lyric timeline (see `timeline.py`) says *when* each line is sung. The manifest says
*what is on screen* for each stretch of the song: which image, whether it is a still with a Ken-Burns
move or a video clip, and which lyric line the shot illustrates. The renderer (`render.py`) is a **pure
function** of this manifest plus the referenced asset files — so a gate reviews the manifest instead of
a re-render, a single shot can be regenerated and re-rendered, and the whole run is resumable.

Per shot (the fields WI 1004 fixed by contact with a real edit):
  index, section, lines[], t_start, t_end, kind (still|kenburns|video), prompt, asset, kb

  * lines[]  -- the lyric line(s) this shot illustrates: [{index, text}]
  * kind     -- `still`/`kenburns` render an image (kenburns = with a move); `video` plays a clip
  * prompt   -- the image prompt that produced (or would regenerate) the still; the lyric+brief join
  * asset    -- path to the still PNG or the video clip, relative to the manifest file
  * kb       -- Ken-Burns move for still/kenburns shots: {zoom: in|out|none, pan: c|l|r|u|d}; ignored
                for `video`

An optional `loop` block (length, crossfade, search, blend_at) says how to finish the cut into a
seamless loop —
see `loop_finish.py`. It is absent from a manifest for a standalone cut, and every manifest written
before it existed loads unchanged.

Shots partition the song with no gaps or overlaps: shot 0 starts at 0, each shot's t_end is the next
shot's t_start, and the last shot's t_end is the song duration. A gap would render as black; validation
refuses it.

Pure stdlib; no ffmpeg, no model code, no network -- so it validates without a GPU or a human.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

KINDS = ("still", "kenburns", "video")
ZOOMS = ("in", "out", "none")
PANS = ("c", "l", "r", "u", "d")
EPS = 0.05  # partition tolerance in seconds


@dataclass
class Shot:
    index: int
    section: str
    lines: list[dict]          # [{"index": int, "text": str}]
    t_start: float
    t_end: float
    kind: str
    prompt: str
    asset: str
    kb: dict = field(default_factory=lambda: {"zoom": "in", "pan": "c"})

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


@dataclass
class Loop:
    """How to finish this cut into a seamless loop (WI 1159); absent means "no loop cut".

    `length` is the authored loop point in seconds — a section start, a lyric onset, whatever the author
    chose. `crossfade` is the wrap blend. `search` lets the loop finish refine `length` BACKWARDS by up
    to that many seconds to land on better-matching material; 0 uses the authored length exactly. The
    `blend_at` says where the wrap's dissolve sits: `end` (default) opens a single pass on clean
    material and closes by dissolving back toward it; `start` opens mid-dissolve. The two are rotations
    of one cycle and loop identically (WI 1181). The mechanism is `loop_finish.py`; these four values are
    the creative decision, which is why they live here and not there.
    """
    length: float
    crossfade: float = 0.75
    search: float = 0.0
    blend_at: str = "end"


@dataclass
class Manifest:
    audio: str
    duration: float
    source_timeline: str
    shots: list[Shot] = field(default_factory=list)
    notes: str = ""
    loop: Loop | None = None


class ManifestError(ValueError):
    """A manifest is malformed. Raised at emit/validate time so a bad manifest never reaches render."""


def partition_shots(timeline, group_sizes: list[int]) -> list[Shot]:
    """Group a timeline's lines into shot skeletons (timing + lines + section only).

    `group_sizes` sums to the line count; group i takes the next `group_sizes[i]` lines. A shot's
    t_start is its first line's start (shot 0 is forced to 0 to cover any intro); its t_end is the next
    shot's t_start, and the last shot's t_end is the song duration (to cover any outro). The creative
    fields (kind/prompt/asset/kb) are placeholders for a driver to fill.
    """
    if sum(group_sizes) != len(timeline.lines):
        raise ManifestError(
            f"group_sizes sum {sum(group_sizes)} != {len(timeline.lines)} timeline lines")
    # Slice line indices per group.
    groups: list[list] = []
    cursor = 0
    for n in group_sizes:
        groups.append(timeline.lines[cursor:cursor + n])
        cursor += n
    shots: list[Shot] = []
    for i, grp in enumerate(groups):
        t_start = 0.0 if i == 0 else grp[0].start
        # t_end: next group's first line start, or the song duration for the last group.
        t_end = groups[i + 1][0].start if i + 1 < len(groups) else timeline.duration
        shots.append(Shot(
            index=i,
            section=grp[0].section,
            lines=[{"index": ln.index, "text": ln.text} for ln in grp],
            t_start=round(float(t_start), 3),
            t_end=round(float(t_end), 3),
            kind="still",
            prompt="",
            asset="",
        ))
    return shots


def validate(m: Manifest, *, manifest_dir: Path | None = None) -> None:
    """Reject a malformed manifest rather than handing it to the renderer.

    A silently-broken manifest (a gap that renders black, a missing asset, a bad kind) is far more
    expensive to debug downstream than a loud failure here. When `manifest_dir` is given, asset paths
    are resolved against it and their existence on disk is checked.
    """
    if not m.shots:
        raise ManifestError("manifest has no shots")
    if m.duration <= 0:
        raise ManifestError(f"non-positive audio duration {m.duration}")
    if abs(m.shots[0].t_start) > EPS:
        raise ManifestError(f"shot 0 must start at 0, starts at {m.shots[0].t_start}")
    if abs(m.shots[-1].t_end - m.duration) > EPS:
        raise ManifestError(
            f"last shot ends at {m.shots[-1].t_end}, must equal duration {m.duration}")
    if not m.audio.strip():
        raise ManifestError("manifest has no audio")
    if manifest_dir is not None and not (manifest_dir / m.audio).resolve().is_file():
        raise ManifestError(f"audio not found: {(manifest_dir / m.audio).resolve()}")
    if m.loop is not None:
        lp = m.loop
        if lp.length <= 0:
            raise ManifestError(f"loop.length must be positive, got {lp.length}")
        if lp.crossfade <= 0:
            raise ManifestError(f"loop.crossfade must be positive, got {lp.crossfade}")
        if lp.search < 0:
            raise ManifestError(f"loop.search must not be negative, got {lp.search}")
        if lp.search >= lp.length:
            raise ManifestError(f"loop.search {lp.search} >= loop.length {lp.length}: the search "
                                f"window runs past the start of the cut")
        if lp.crossfade >= lp.length - lp.search:
            raise ManifestError(f"loop.crossfade {lp.crossfade} is not shorter than the shortest "
                                f"candidate length {lp.length - lp.search}")
        if lp.blend_at not in ("start", "end"):
            raise ManifestError(f"loop.blend_at must be 'start' or 'end', got {lp.blend_at!r}")
        if lp.length + lp.crossfade > m.duration + EPS:
            raise ManifestError(f"loop needs {lp.length + lp.crossfade}s of material but the cut is "
                                f"{m.duration}s")
    prev_end = 0.0
    for i, s in enumerate(m.shots):
        if s.index != i:
            raise ManifestError(f"shot at position {i} has index {s.index}")
        if s.kind not in KINDS:
            raise ManifestError(f"shot {i}: unknown kind {s.kind!r}")
        if not s.prompt.strip():
            raise ManifestError(f"shot {i}: empty prompt")
        if not s.asset.strip():
            raise ManifestError(f"shot {i}: empty asset")
        if s.t_end <= s.t_start:
            raise ManifestError(f"shot {i}: t_end {s.t_end} not after t_start {s.t_start}")
        if abs(s.t_start - prev_end) > EPS:
            raise ManifestError(
                f"shot {i}: t_start {s.t_start} leaves a gap/overlap after {prev_end}")
        if s.kb.get("zoom", "in") not in ZOOMS:
            raise ManifestError(f"shot {i}: bad kb.zoom {s.kb.get('zoom')!r}")
        if s.kb.get("pan", "c") not in PANS:
            raise ManifestError(f"shot {i}: bad kb.pan {s.kb.get('pan')!r}")
        if manifest_dir is not None:
            ap = (manifest_dir / s.asset).resolve()
            if not ap.is_file():
                raise ManifestError(f"shot {i}: asset not found: {ap}")
        prev_end = s.t_end


def to_json(m: Manifest, *, manifest_dir: Path | None = None) -> str:
    validate(m, manifest_dir=manifest_dir)
    return json.dumps(asdict(m), indent=2) + "\n"


def from_json(text: str) -> Manifest:
    d = json.loads(text)
    shots = [Shot(**s) for s in d["shots"]]
    loop = Loop(**d["loop"]) if d.get("loop") else None
    return Manifest(audio=d["audio"], duration=d["duration"],
                    source_timeline=d["source_timeline"], shots=shots, notes=d.get("notes", ""),
                    loop=loop)


def write(m: Manifest, path: Path) -> Path:
    """Write the manifest JSON, validating assets relative to its own directory first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(m, manifest_dir=path.parent))
    return path
