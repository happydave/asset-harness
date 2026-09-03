# Track: music-video

**Status:** 🟡 in progress — the track is open, its **[license lane](license-lane.md)** is written, and
the **lyric-timing question is answered**: post-hoc alignment (Demucs → WhisperX → reconcile against
the authored sheet) aligned all 16 lines of a real ACE-Step vocal song at high confidence in 39 s on
CPU ([findings](findings/2026-07-22-lyric-alignment-posthoc.md)). The **model-native timing route was
investigated and declined** (WI 1003: real feature, but not reachable as a ComfyUI node and blocked on
our XL checkpoint's missing layer config — post-hoc stays the sole route). **Motion clips are blocked**
on `ai2` by an fp8/ROCm wheel gap (below). The **walking skeleton is built** (WI 1004): a shot-list
manifest → pure renderer → a 75 s / 7.1 MB Clamor lobby cut, end to end
([findings](findings/2026-07-24-lobby-skeleton.md)), and the **loop-seam finish is built** (WI 1159):
the same render now also emits a **56.0 s seamless loop** whose join is adjacent source material by
construction ([findings](findings/2026-08-25-loop-seam-finish.md)). Discovery:
[WI 989](../../../tickets/docs/pending/989-ah-music-video-track/discover.md).

**Operating the pipeline (making a video)?** Read [`AGENTS.md`](AGENTS.md) — a one-screen card of the
commands, rules and nevers — and the model skill for each step. The rest of this README is the
track's record, for developing the pipeline.

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
| Motion clips | **Wan2.2 i2v 14B** | Apache-2.0 | `ai2` — two-stage **fp8**, **~127 s/clip**, see below |
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

### Motion clips work — two-stage fp8 (`wan2.2-test`), ~127 s/clip

Wan i2v is usable on `ai2` at **~127 s/clip**. Use `generate_clip.py` (fp8 is the default), which
replicates ai2's saved `wan2.2-test` workflow: **both experts**, the schedule split 2/2 (high-noise steps
0→2 → low-noise 2→4), both `lightx2v_4steps` LoRAs, 4 steps, cfg 1, euler/simple, shift 5,
1280×720 × 33 f. The July clips were cut at fp16, which is 3.0× slower and spills to lowvram; fp8 costs
a marginal softness (WI 1161).

**`ai2` must be running ComfyUI with `--disable-mmap`.** Without it, one checkpoint load takes 35.8 min
instead of 6 s — that flag is worth ~360× on a load, against fp8-vs-fp16's 3×. It is a shared service:
check it, don't change it unilaterally. `prototypes/preflight.py` checks it, along with every other
operational precondition below, and prints the fix for anything that fails — run it first.

Full recipe, VRAM limits, and the clip-chaining technique for longer continuous shots:
[`skills/prompting-wan-i2v/SKILL.md`](../skills/prompting-wan-i2v/SKILL.md) and
[findings](findings/2026-08-24-production-sessions.md).

**This reverses three earlier readings, each of which was correct about the configuration it tested:**

- *"fp8 falls back to dequantisation"* (WI 1002) — real, and fixed by the `torch 2.10.0+rocm7.0` wheel
  swap in WI 1013.
- *"loading the two 14 GB checkpoints dominates, so video is impractical"* (WIs 1013/1015) — the
  ~36 min-per-checkpoint load was the **mmap page-fault stall**, not fp8 weight preparation. With
  `--disable-mmap` the same checkpoint loads in **6 s** (WI 1161). Note the 2/2 split does *not* keep
  both stages resident, as was assumed for a while — ComfyUI evicts between stages at either dtype; the
  reload is simply cheap.
- *"shots are stills plus Ken Burns only"* (WI 1004) — retired. The hybrid edit noted above is now a
  deliberate choice rather than a hardware limit.

**Two input rules**, learned early and still true:

- **Feed opaque stills only.** An RGBA sprite makes the model spend its capacity inventing a
  background. Composite onto a real background first.
- **Expect title-card text hallucination** on centred-subject inputs (an early clip grew the words
  `PEONG` and `FROMT`). The stock negative prompt lists subtitles and did not prevent it — and note
  that at the production recipe's cfg 1, negatives are inert entirely.

### Wan2.2 is the only sanctioned video model

Use **Wan2.2** (Apache-2.0) for image-to-video. Do not use the LTX-2.3 blueprints, even though `ai2`
ships them and they are the more convenient thing on the box: LTX is under the Lightricks community
license (free below $10M revenue, a separate commercial agreement above it), which does not meet this
repo's clean-license bar. HunyuanVideo (Tencent community license, MAU-gated) and Stable Video
Diffusion (Stability community license) fail the same bar. CogVideoX-1.5/2B is Apache-2.0 and is the
one clean fallback worth knowing about — CogVideoX-5B is not.

**The clean choice is not the default choice on this box.** That is why it is written down.

## Contents

- [`AGENTS.md`](AGENTS.md) — the operator card: how to make a video, in one screen.
- [`license-lane.md`](license-lane.md) — the vocal/lyrics license lane. **Required reading before
  generating.**
- `prototypes/`
  - [`preflight.py`](prototypes/preflight.py) — **run first.** Checks every operational precondition
    (server up, `--disable-mmap` on, queue idle and not in the load hang, last job not Wan, recipe
    checkpoints/LoRAs/encoders/VAEs installed, workstation ffmpeg, track venvs) and prints the fix for
    each failure; exit 1 on any failure so drivers can gate on it. Read-only. `--stage` narrows it.
    [`test_preflight.py`](prototypes/test_preflight.py) (57 checks, no server or GPU needed).
  - [`select_song.py`](prototypes/select_song.py) — **the song stage** (WI 1176): a song spec JSON
    (`inputs/clamor_hold_the_line.song.json` is the template) → seed sweep on `ai2` → save-time QC
    (ceiling + truncation veto) → Audiobox CE rank in the scoring venv
    ([`scoring/score_audiobox.py`](prototypes/scoring/score_audiobox.py)) → `machine-auto` pick →
    `<name>.song.json` record built from the substrate dataclasses; `--into MANIFEST` lands the song
    block. A truncated candidate is never promoted; no CE score means no pick (exit 1, owner re-picks).
    [`test_select_song.py`](prototypes/test_select_song.py) (24 checks).
  - [`generate_song.py`](prototypes/generate_song.py) — ACE-Step 1.5 with lyrics; `--seeds a,b,c`
    gives the 3–5 candidates the pick gate wants. The graph, checkpoint arms and save-time
    postprocess that `select_song.py` reuses.
  - [`timeline.py`](prototypes/timeline.py) — the lyric timeline (JSON + LRC). **Every route emits
    this**, so the shot list cannot tell which produced it. Validates at emit time.
  - [`manifest.py`](prototypes/manifest.py) — the **shot-list manifest** schema (the track's durable
    artifact): timeline → 8 shots, each `{lines, t_start/t_end, kind, prompt, asset, kb}`; validates a
    contiguous partition + asset existence at emit, plus the optional `loop` block and the optional
    **candidate layer** (WI 1175, the promotion substrate): per-shot and song candidate/pick records
    with verdict + provenance, so a finished manifest answers *what else was tried, who chose, and
    why*. [`test_manifest.py`](prototypes/test_manifest.py) (49 checks).
  - [`repick.py`](prototypes/repick.py) — change a pick **within the recorded candidates** (no
    regeneration, override recorded to pick history) and audit staleness: records whose provenance no
    longer matches current upstream choices. [`test_repick.py`](prototypes/test_repick.py) (26 checks).
  - [`render.py`](prototypes/render.py) — the **pure renderer**: manifest + assets → mp4 (zoompan Ken
    Burns with the pre-upscale fix, xfade chain, audio mux, web encode). No creative decisions live
    here — the whole edit is a function of the manifest. A manifest carrying a `loop` block also gets
    the loop cut, alongside the full one.
  - [`loop_finish.py`](prototypes/loop_finish.py) — the **loop-seam finish**: wrap-crossfade a cut so
    its end-to-start join is adjacent source material, then measure both joins and the codec padding.
    The dissolve sits at the end by default, so a single pass opens clean and the repeat is unchanged.
    [`test_loop.py`](prototypes/test_loop.py) (49 checks).
  - [`build_lobby.py`](prototypes/build_lobby.py) — the WI 1004 skeleton driver: authors the 8-shot
    manifest, generates missing stills on `ai2`, interpolates the hero clip, emits the manifest.
  - [`generate_still.py`](prototypes/generate_still.py) — opaque Z-Image text-to-image stills.
  - [`interpolate.py`](prototypes/interpolate.py) — workstation ffmpeg `minterpolate` fps raise (the
    WI 1019 smoothness fix for Wan clips).
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
| ~~1003~~ | ~~SPIKE — custom ComfyUI node exposing ACE-Step lyric timestamps~~ | **done — no node.** The feature is real & cross-attention-derived, but the port dropped the whole alignment subsystem and our XL checkpoint lacks its layer config; post-hoc stays the sole route ([findings](findings/2026-07-23-acestep-native-lyric-timing.md)) |
| ~~1004~~ | ~~Walking skeleton — 60 s Clamor lobby loop, end to end~~ | **done — pipeline runs end to end.** manifest → pure renderer → 75 s / 7.1 MB lobby loop; `manifest.py` + `render.py` are the reusable core ([findings](findings/2026-07-24-lobby-skeleton.md)). Owner `[human]` review closed 2026-08-24; the loop-seam finish is [WI 1159](../../../tickets/docs/pending/1159-ah-music-video-loop-seam-finish/workitem.md), **done 2026-08-25** |
| ~~1179~~ | ~~SPIKE — VLM-as-judge for still selection~~ | **done — verdict: neither.** Two Qwen3-VL sizes × three protocols × two archived corpora: top-1 0/2 and 2/6, below PickScore and below "answer the first one". The gate/selector split is now 3-for-3, and presentation order turned out to be a confound worth more than the verdict ([findings](findings/2026-08-28-vlm-judge.md)) |
| ~~1159~~ | ~~Loop-seam finish for videos intended to loop~~ | **done** — `loop_finish.py` + a manifest `loop` block; the lobby cut now also renders a 56.0 s seamless loop, gates measured ([findings](findings/2026-08-25-loop-seam-finish.md)) |
| ~~1181~~ | ~~Put the wrap's dissolve at the end~~ | **done** — owner feedback on 1159: the dissolve now sits at the end, so a single pass opens clean; the repeat is the same cycle. Also corrected the level measurement (the old window lay inside the crossfade) |

Detail lives in [`tickets/docs/pending/`](../../../tickets/docs/pending/) and in the
[project backlog](../../../tickets/docs/projects/asset-harness/project.md).
