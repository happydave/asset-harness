# Track: music-video

**Status:** ⚪ not started — the track is open and its **[license lane](license-lane.md)** is written;
no prototype has run yet. First work: the two alignment spikes and the Wan2.2 cost spike
(WIs 1001–1003), then a 60-second walking skeleton (WI 1004). Discovery:
[WI 989](../../../tickets/docs/pending/989-ah-music-video-track/discover.md).

## Purpose

Produce a complete **lyric-driven music video**: an AI-generated song *with vocals*, plus images and
video clips timed to its lyrics, assembled into one deliverable.

**This track's output is a media artifact, not a game-importable asset.** That makes it the odd one
out here — every other track produces an asset class a game imports through a thin downstream step.
This one *composes* the existing tracks (`audio` for the song, `2d` for stills, `vfx`/Wan for motion)
and adds a timing and assembly layer of its own. It is listed among the tracks because it follows the
same discovery → prototypes → harness lifecycle, not because it produces an asset class.

**First consumer:** a lobby video for [Clamor](../../../tickets/docs/projects/clamor/project.md), plus
a promo test run.

## The rule (read this before generating anything)

**Vocal music is permitted for standalone media artifacts** — lobby videos, promos, trailers.

**Vocal music remains prohibited as a shipped in-game audio asset.** There, the `audio` track's rule
governs unchanged: *instrumental/ambient only for shipped assets*. This track is a **bounded exception
to that rule, not a repeal of it** — a music bed that plays inside the game is `audio` track work and
the answer is still no.

Cleanliness here is **per-output**, not a property of the model: ACE-Step's MIT weights say nothing
about whether a given set of lyrics infringes. Four checks establish it — lyric originality, voice
likeness, melodic familiarity, and prompt hygiene — each bound to a pipeline gate.

**→ [`license-lane.md`](license-lane.md)** — the six exposures separated by kind (lyric text is
copyright; vocal likeness is right of publicity — they are not the same problem), the prompt-hygiene
rules, the gate each check runs at, and what a findings entry must record.

## Approach

| Stage | Tool | License | Where |
|---|---|---|---|
| Music + lyrics | **ACE-Step 1.5** (`acestep_v1.5_xl_base_bf16`) | MIT | `ai2` (ComfyUI) |
| Candidates (3–5) | same graph, `batch_size` / seed sweep | — | `ai2` |
| Lyric→time alignment | **Demucs** → **WhisperX**, and/or a model-native route | MIT / BSD-2-Clause | route undecided — WIs 1001 / 1003 |
| Stills | **Z-Image** (Turbo / Base / Z-Anime) | Apache-2.0 | `ai2` |
| Motion clips | **Wan2.2 i2v 14B** | Apache-2.0 | `ai2` |
| Assembly | **ffmpeg** (concat / zoompan / xfade) | — | **workstation** |

- **Generation is remote, assembly is local.** `ai2` has no ffmpeg — a constraint the `audio` track
  already works under (see the header of
  [`audio/prototypes/optimize_audio.py`](../audio/prototypes/optimize_audio.py)). Generated artefacts
  and a manifest come back to the workstation, and the render happens there.
- **The durable artifact is the shot-list manifest, not the video.** Per shot: lyric line, start/end
  time, section tag, image prompt, `kind` (`still` / `kenburns` / `video`), asset ref. The renderer is
  a pure function of it. That is what makes the review gates cheap (review a manifest, not a
  re-render), makes a single shot regenerable, and makes a run resumable.
- **Hybrid by design.** Stills with Ken Burns for most shots, Wan clips for a hero moment or two. A
  3-minute song at ~5 s per clip is ~36 generations, and constant motion on every shot reads as noise
  — so this is the better edit as well as the cheaper one.

### Wan2.2 is the only sanctioned video model

Use **Wan2.2** (Apache-2.0) for image-to-video. Do not use the LTX-2.3 blueprints, even though `ai2`
ships them and they are the more convenient thing on the box: LTX is under the Lightricks community
license (free below $10M revenue, a separate commercial agreement above it), which does not meet this
repo's clean-license bar. HunyuanVideo (Tencent community license, MAU-gated) and Stable Video
Diffusion (Stability community license) fail the same bar. CogVideoX-1.5/2B is Apache-2.0 and is the
one clean fallback worth knowing about — CogVideoX-5B is not.

**The clean choice is not the default choice on this box.** That is why it is written down.

## Contents

- `license-lane.md` — the vocal/lyrics license lane. Required reading before generating.
- `prototypes/`, `findings/` — created when work starts; use
  [`../_template/findings.md`](../_template/findings.md), plus the extra records the license lane
  requires.

## Open work

| WI | Title | Why it comes first |
|---|---|---|
| 1001 | SPIKE — lyric→time alignment via Demucs + WhisperX (post-hoc) | the spike that decides the track's shape |
| 1002 | SPIKE — one Wan2.2 i2v clip on `ai2` | ROCm viability + wall-clock; deliverable is a number |
| 1003 | SPIKE — custom ComfyUI node exposing ACE-Step lyric timestamps | model-native route, complementary to 1001 |
| 1004 | Walking skeleton — 60 s Clamor lobby loop, end to end | prove the artifact before building the gates |

Detail lives in [`tickets/docs/pending/`](../../../tickets/docs/pending/) and in the
[project backlog](../../../tickets/docs/projects/asset-harness/project.md).
