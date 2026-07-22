# Track: music-video

**Status:** 🟡 in progress — the track is open, its **[license lane](license-lane.md)** is written, and
the **lyric-timing question is answered**: post-hoc alignment (Demucs → WhisperX → reconcile against
the authored sheet) aligned all 16 lines of a real ACE-Step vocal song at high confidence in 39 s on
CPU ([findings](findings/2026-07-22-lyric-alignment-posthoc.md)). **Motion clips are blocked** on `ai2` by an fp8/ROCm wheel gap (below). Remaining: the
model-native timing route and a 60-second walking skeleton (WIs 1003–1004). Discovery:
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
| Lyric→time alignment | **Demucs** → **WhisperX** → reconcile *(default route)*; owner-tap as the floor | MIT / BSD-2-Clause | **workstation**, track-local `.venv`, CPU |
| Stills | **Z-Image** (Turbo / Base / Z-Anime) | Apache-2.0 | `ai2` |
| Motion clips | **Wan2.2 i2v 14B** | Apache-2.0 | `ai2` — **currently unusable**, see below |
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

### ⚠ Motion clips are blocked on `ai2` (fp8 → dequantisation fallback)

**Do not plan on Wan clips from `ai2` until this is fixed.** One 5-second clip takes **~45+ minutes**
against a ~97 s reference on comparable CUDA hardware. Cause, stated by ComfyUI's own log:

```
FP8 _scaled_mm failed: Float8_e4m3fn is only supported for ROCm 6.5 and above,
falling back to dequantization
```

ComfyUI's torch is `2.9.1+rocm6.4` (HIP 6.4) while the box's `rocm-core` is **7.2.4** — one wheel
built 0.1 behind the threshold. `_scaled_mm` is the matmul, so this hits inference, not just loading,
and it affects **every fp8 model on that box**, silently (it is a warning, not an error).

Fix: upgrade the torch wheel in `/opt/comfyui-env` to a ROCm ≥ 6.5 build (fixes fp8 box-wide), or use
the fp16 Wan checkpoints (fixes Wan only, 28.6 GB per stage). Detail:
[findings](findings/2026-07-22-wan22-i2v-rocm-fp8.md).

Until then, shots are **stills plus Ken Burns only**.

### Wan2.2 is the only sanctioned video model

Use **Wan2.2** (Apache-2.0) for image-to-video. Do not use the LTX-2.3 blueprints, even though `ai2`
ships them and they are the more convenient thing on the box: LTX is under the Lightricks community
license (free below $10M revenue, a separate commercial agreement above it), which does not meet this
repo's clean-license bar. HunyuanVideo (Tencent community license, MAU-gated) and Stable Video
Diffusion (Stability community license) fail the same bar. CogVideoX-1.5/2B is Apache-2.0 and is the
one clean fallback worth knowing about — CogVideoX-5B is not.

**The clean choice is not the default choice on this box.** That is why it is written down.

## Contents

- [`license-lane.md`](license-lane.md) — the vocal/lyrics license lane. **Required reading before
  generating.**
- `prototypes/`
  - [`generate_song.py`](prototypes/generate_song.py) — ACE-Step 1.5 with lyrics; `--seeds a,b,c`
    gives the 3–5 candidates the pick gate wants.
  - [`timeline.py`](prototypes/timeline.py) — the lyric timeline (JSON + LRC). **Every route emits
    this**, so the shot list cannot tell which produced it. Validates at emit time.
  - [`align_posthoc.py`](prototypes/align_posthoc.py) — Demucs → WhisperX → reconcile against the
    authored sheet. The default route. Needs the track-local venv.
  - [`tap_align.py`](prototypes/tap_align.py) — tap ENTER per line. The floor: stdlib + `ffplay`,
    nothing to install, and it cannot be defeated by melisma.
  - [`generate_clip.py`](prototypes/generate_clip.py) — Wan2.2 image-to-video, both regimes.
  - [`test_timeline.py`](prototypes/test_timeline.py) — `python3 test_timeline.py`, 35 checks.
- `findings/` — per [`../_template/findings.md`](../_template/findings.md), **plus** the vocal flag,
  intended use, lyric provenance and check table the [license lane](license-lane.md) requires.

### Environment

Song and clip generation are ComfyUI-over-HTTP and need only the system `python3` + `requests`.
**Alignment needs a track-local venv** (git-ignored, ~7.6 GB — `whisperx` pins its own CUDA torch):

```
python3 -m venv .venv && .venv/bin/pip install demucs whisperx
.venv/bin/python prototypes/align_posthoc.py --audio ... --lyrics ...
```

## Open work

| WI | Title | Why it comes first |
|---|---|---|
| ~~1001~~ | ~~SPIKE — lyric→time alignment via Demucs + WhisperX~~ | **done** — post-hoc adopted as the default route ([findings](findings/2026-07-22-lyric-alignment-posthoc.md)) |
| ~~1002~~ | ~~SPIKE — one Wan2.2 i2v clip on `ai2`~~ | **done** — ~45+ min/clip; root cause is a torch wheel built against ROCm 6.4 ([findings](findings/2026-07-22-wan22-i2v-rocm-fp8.md)) |
| 1003 | SPIKE — custom ComfyUI node exposing ACE-Step lyric timestamps | model-native route, complementary to 1001 |
| 1004 | Walking skeleton — 60 s Clamor lobby loop, end to end | prove the artifact before building the gates |

Detail lives in [`tickets/docs/pending/`](../../../tickets/docs/pending/) and in the
[project backlog](../../../tickets/docs/projects/asset-harness/project.md).
