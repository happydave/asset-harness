# Findings: ambient music beds via ACE-Step 1.5

**Date:** 2026-06-24
**Track:** audio (music sub-stream)
**Verdict:** works

## Goal

Stand up the music sub-stream: **instrumental ambient** loop beds for the games (DWA space ambience,
Sounding/Scrapper exploration + tension), on the clean ACE-Step 1.5 stack. First set:
`ambient_deep_space`, `ambient_exploration`, `ambient_tense`.

## Tooling

- **Base model:** ACE-Step 1.5 **base** (`acestep_v1.5_xl_base_bf16.safetensors`). The blueprint's
  `acestep_v1.5_turbo` checkpoint is **not** installed on `ai2`, so we drive the base model with
  real sampler settings instead of the turbo 8-step/cfg-1 defaults.
- **Encoders / VAE:** `DualCLIPLoader(qwen_0.6b_ace15 + qwen_4b_ace15, type=ace)`, `ace_1.5_vae`.
- **Workflow:** graph from the ComfyUI "Text to Audio (ACE-Step 1.5)" blueprint, adapted —
  `UNETLoader → ModelSamplingAuraFlow(shift 3) → KSampler(euler, simple, 40 steps, cfg 5)`,
  `TextEncodeAceStepAudio1.5(tags, lyrics="", bpm, key, duration)` + `ConditioningZeroOut` negative,
  `EmptyAceStep1.5LatentAudio → VAEDecodeAudio → SaveAudio`. Script:
  [`prototypes/music/generate_music.py`](../prototypes/music/generate_music.py). Post (loop):
  [`prototypes/optimize_audio.py`](../prototypes/optimize_audio.py).

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| ACE-Step 1.5 (weights) | **MIT** | yes | yes (with notice) | https://github.com/ace-step/ACE-Step-1.5 |
| Training data | licensed + royalty-free/public-domain + synthetic (MIDI→audio) — **vendor claim** | — | — | model card |

- **Effective output license:** MIT — the cleanest of any model the harness uses (beats Stable
  Audio's revenue-gated Community License).
- **Safe for a clean/commercial pack?** Yes — **provided music stays instrumental**. Lyrics are
  always empty here; vocal style-mimicry is the real exposure regardless of the MIT weights.

## Hardware

- **Machine / GPU:** ai2, gfx1201 (R9700), AMD ROCm. **~27 s** to generate 45 s of 48 kHz stereo at
  40 steps — fast. (First confirmed ACE-Step 1.5 base run on this box.)

## Inputs

- **Tags (per track):** comma-separated genre/instrument/mood lists, e.g. deep_space = "ambient,
  dark ambient, space, slow evolving synth pads, deep drones, sub bass, no drums, no vocals,
  cinematic, vast, lonely". **Lyrics empty.** See `TRACKS[]` in `generate_music.py`.
- **Per track:** bpm (60/70/80), keyscale (A minor / C major / D minor), duration 45 s, seeds
  501–503; `cfg_scale` 2, temperature 0.85, top_p 0.9.
- **Sampler:** euler / simple, 40 steps, cfg 5, AuraFlow shift 3, denoise 1.

## Result

- **Samples:** [`samples-2026-06-24-music/`](samples-2026-06-24-music/) (3 looped `.ogg`).
- **What worked:** healthy, musical, dynamic output (raw RMS −14 to −15.4 dB, peak −1.8 dB; not
  silent/clipped). Post authors seamless 43.5 s loops (45 − 1.5 s crossfade), 48 kHz. Loudness:
  exploration −23.1, tense −22.3 (on target); deep_space −25.0 (~2 LU under −23 — single-pass
  loudnorm tolerance on dynamic material; fine for a background bed).
- Audible musicality/coherence audition is the operator's.

## Repeatability

- Deterministic given seed. Tag vocabulary steers genre/mood well. Loop + loudness are post flags.

## Next

- Tune per-game (volume ducking under SFX; longer beds if 45 s reads as repetitive).
- DWA/Sounding import when a music-bed playback layer exists (not wired yet).
- If deep_space loudness matters, two-pass loudnorm; otherwise leave as a background bed.
