# Findings: post-hoc lyric alignment (Demucs → WhisperX) — and the tap floor

**Date:** 2026-07-22
**Track:** music-video
**Verdict:** works

## Goal

Decide how the `music-video` track gets **line-level lyric timings**, which everything downstream
depends on: which image belongs to which lyric, where the cuts fall, the whole edit.

ACE-Step 1.5 derives per-line timestamps upstream from its own cross-attention, but **that is not
reachable from the ComfyUI nodes this harness drives** — `TextEncodeAceStepAudio1.5.execute()` returns
`CONDITIONING` and nothing else, and the ACE extension registers no timestamp output at all. So timing
has to come from somewhere else. This is the post-hoc route: separate the vocal, recognise it, and
reconcile against the lyrics we already know we asked for.

Also builds the **owner-tap fallback**, so the track ships regardless of how the automated route lands.

## Tooling

- **Song:** ACE-Step 1.5 base (`acestep_v1.5_xl_base_bf16.safetensors`) via ComfyUI on `ai2` —
  the `audio` track's graph with the `lyrics` field populated.
  [`prototypes/generate_song.py`](../prototypes/generate_song.py).
- **Separation:** Demucs 4.1.0, `htdemucs`, `--two-stems vocals`.
- **Recognition:** WhisperX 3.8.6 — faster-whisper `small.en` transcribe + wav2vec2
  (`wav2vec2_fairseq_base_ls960_asr_ls960`) word-level forced alignment. **Diarization not used.**
- **Reconciliation:** `difflib.SequenceMatcher` over normalised tokens — stdlib.
  [`prototypes/align_posthoc.py`](../prototypes/align_posthoc.py).
- **Format:** [`prototypes/timeline.py`](../prototypes/timeline.py) — JSON + LRC, emitted by every
  route so the shot list cannot tell which produced it. 35 regression checks in
  [`prototypes/test_timeline.py`](../prototypes/test_timeline.py).
- **Fallback:** [`prototypes/tap_align.py`](../prototypes/tap_align.py) — `ffplay` + one ENTER per
  line. Stdlib only.
- **Environment:** track-local `music-video/.venv` (git-ignored), created with the system `python3`.
  No `sudo`, nothing outside the repo and `~/.cache`.

## Licensing (commercial / redistribution)

Two separate chains: the one that made the audio, and the one that analysed it.

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| ACE-Step 1.5 (weights) | **MIT** | yes | yes (with notice) | https://github.com/ace-step/ACE-Step-1.5 |
| ACE-Step training data | licensed + royalty-free + synthetic — **vendor claim** (Supported, not audited) | — | — | model card |
| Demucs (code + `htdemucs`) | **MIT** | yes | yes | https://github.com/facebookresearch/demucs |
| WhisperX | **BSD-2-Clause** | yes | yes | https://github.com/m-bain/whisperX |
| wav2vec2 align model (torchaudio) | MIT (torchaudio) | yes | yes | pytorch.org/torchaudio |
| pyannote-audio (pulled in as a whisperx dependency) | CC-BY-4.0, some models HF-gated | — | — | **not used** — diarization is disabled |

- **Effective output license:** **MIT** for the song. Demucs/WhisperX/wav2vec2 are *analysis* tools —
  they read the audio and emit timings; they contribute nothing to the audio itself, so they do not
  enter the audio's license chain.
- **Safe for a clean pack?** The song is a **vocal** output and therefore governed by
  [`../license-lane.md`](../license-lane.md), not by the license alone: permitted for standalone media
  artifacts, still prohibited as a shipped in-game audio asset.
- **pyannote is worth naming.** WhisperX pulls it in as a hard dependency, and its models are
  CC-BY-4.0 and partly HF-gated. Diarization is off (single vocalist), so it is installed but never
  invoked — a dependency, not a link in any chain. Do not enable diarization without revisiting this.

### License-lane checks (first vocal output under the lane)

| Check | Gate | Outcome |
|---|---|---|
| Lyric originality | lyrics | **pass** — authored original for this project; no existing lyrics used as input |
| Voice likeness | candidate-pick | **pass** — no artist named in the tags; style described by genre, instrumentation, vocal character |
| Melodic familiarity | candidate-pick | **pass** — no song steered at; owner ear check outstanding |
| Prompt hygiene (shots) | shot-list | **n/a** — no shots in this work item |

- **Vocal flag:** yes.
- **Intended use:** unpublished test artifact; may be reused by WI 1004's lobby loop.

## Hardware

- **Song:** `ai2`, gfx1201 (R9700), ROCm. **117 s** to generate 75 s of 48 kHz stereo at 40 steps.
- **Alignment:** workstation, **CPU only** (Ryzen; the RTX 5070 was not used). 75 s of audio does not
  need a GPU, and CPU sidestepped the Blackwell/sm_120 CUDA-version question entirely.

## Inputs

- **Tags:** `post-apocalyptic folk rock, male and female vocals, gritty clean vocal, acoustic guitar,
  driving drums, bass, mournful strings, minor key, anthemic chorus, weary, defiant, cinematic`
- **Lyrics:** 16 lines, `[verse]`/`[chorus]`/`[verse]`/`[chorus]`, Clamor-themed (a scavenging party
  heading home to a colony). Authored for this project.
- **Song params:** 75 s, bpm 96, D minor, 4/4, seed 701, 40 steps, cfg 5, AuraFlow shift 3.
- **Alignment params:** `small.en`, `int8`, `--min-match 0.34`, device cpu.

## Result

**16 of 16 lines aligned at high confidence. 133 words recognised. 39 seconds end to end**
(separation 17 s, ASR + align 23 s), on CPU.

No line required interpolation. **The melisma-as-silence failure mode did not appear.**

```
[00:04.39]Six of us went out at first light
[00:09.39]Counting every step and every round
[00:14.34]The colony is waiting on the far side
[00:19.28]Of a city that has forgotten how to make a sound
[00:23.90]Hold the line, hold the line
...
[01:04.72]We are going home, we are going home tonight
```

### How we know it is right, and not confidently wrong

An aligner producing plausible nonsense looks exactly like one that works, so the output was checked
against a property noise cannot fake. The song sings **the same chorus twice**, as two independent
renditions. Their inter-line intervals:

| | line 1→2 | line 2→3 | line 3→4 |
|---|---|---|---|
| chorus 1 (from 23.90 s) | 3.02 | 2.32 | 2.84 |
| chorus 2 (from 56.62 s) | 2.98 | 2.30 | 2.82 |
| **difference** | **0.04** | **0.02** | **0.02** |

**Agreement within 0.04 s across two separate renditions.** This is a free check whenever a song has
a repeated section, and it is worth doing routinely.

Verse deltas agree less tightly (max 1.01 s, in verse 2's middle lines) — either genuine phrasing
variation or the run's weakest alignment. Either way it is where to look first.

Coverage is plausible *as music*: 4.39 s intro, last line ending at 67.56 s of 75.0 s leaving a 7.4 s
outro, line durations 2.14–5.30 s.

### The raw-mix control overturned an assumption

The [discovery](../../../../tickets/docs/pending/989-ah-music-video-track/discover.md) recorded source
separation as effectively mandatory, citing transcription WER of **47.2% → 27.7%** on mix vs stem.
Running the same alignment with `--skip-separation`:

**Near-identical. Mean start difference 0.12 s; 14 of 16 lines within 0.03 s.** Only two lines
diverged — "Hold the line, hold the line" (0.53 s) and "Count it down and take them one by one"
(1.29 s). And it took 13 s instead of 39 s.

The reason matters more than the number: **that WER figure is for transcription, and this is not
transcription.** We force-align text we already have. Reconciling against the authored sheet decouples
the result from transcription accuracy — a mis-heard word costs one token out of a line instead of
putting a wrong lyric in the output.

**Separation is a quality margin, not a precondition.** Keep it: it costs 17 s and it is what fixed
the two hardest lines. But the discovery's framing was inherited from a paper about a different task.

## Repeatability

Deterministic given the same audio, sheet and model. Re-running the alignment reproduces the timeline;
the *song* is deterministic given the seed. The tap route is by construction not deterministic, which
is fine — it is a measurement of a human.

## Next

- **Route verdict: post-hoc alignment is the track's default.** The owner-tap route stays as the floor
  and as the correction path — it needs no environment at all, and it is the only route that can know
  when the automated one is wrong.
- **[visual/manual], owner:** listen to the song (musical quality; intelligibility is already
  answered by 133 recognised words), and play the `.lrc` against the audio to confirm the words land.
- **WI 1003** (model-native ACE-Step route) now has a fair comparison: same song, same sheet, same
  format, and a measured baseline — 16/16 high confidence, 0.04 s chorus self-consistency, 39 s.
- **For WI 1004:** the chorus self-consistency check is cheap and should be run on every song that has
  a repeated section, as a standing sanity gate before shots are generated against a timeline.
- Consider whether `small.en` is leaving accuracy on the table; a larger model costs seconds, not
  minutes, at this length. Not pursued — the result did not need it.
