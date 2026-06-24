# Findings: SFX set via Stable Audio 3 Medium Base + ffmpeg post

**Date:** 2026-06-23
**Track:** audio (sfx sub-stream)
**Verdict:** works

## Goal

Stand up the audio track's **sfx** path end-to-end: generate game sound effects locally with a
clean-licensed model, post-process them into game-ready loops/one-shots, and prove the import seam
by wiring one into DWA. First set: `ui_click`, `thruster_loop`, `impact_metal`, `station_hum`
(covers one-shots + ambient loops).

## Tooling

- **Base model:** Stable Audio 3 Medium **Base** (`stable_audio_3_medium_base.safetensors`,
  `Comfy-Org/stable-audio-3`). Text encoder: `t5gemma_b_b_ul2.safetensors` (type `stable_audio`).
- **LoRA / ControlNet:** none.
- **Workflow / nodes:** ComfyUI core audio nodes, graph reverse-engineered from the shipped
  "Stable Audio 3 Medium Base" blueprint, minus its optional LLM prompt-expander:
  `CheckpointLoaderSimple → {CLIPLoader(t5gemma) → 2×CLIPTextEncode} + EmptyLatentAudio →
  KSampler(50, cfg 7, lcm, simple) → VAEDecodeAudio → SaveAudio`. Script:
  [`prototypes/sfx/generate_sfx.py`](../prototypes/sfx/generate_sfx.py).
- **Other software:** ffmpeg 6.1.1 (local) for the post step
  [`prototypes/optimize_audio.py`](../prototypes/optimize_audio.py). ai2 has no ffmpeg → post runs
  on the workstation.

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Stable Audio 3 Medium (weights) | Stability AI Community License | yes, **if org revenue < $1M/yr** (Enterprise above) | yes (outputs owned both tiers) | https://huggingface.co/stabilityai/stable-audio-3-medium |
| T5Gemma encoder (bundled) | Gemma Terms of Use | yes (prohibited-use policy applies) | yes, under Gemma terms | https://stability.ai/license |
| Training data | fully licensed: AudioSparx + Freesound (CC0/CC-BY/CCSampling+) | — | — | Stability announcement |

- **Effective output license:** usable commercially; gated by the **<$1M revenue ceiling** and the
  **Gemma prohibited-use** terms.
- **Safe for a clean/commercial asset pack?** Yes for indie/hobby scale (the games qualify);
  **not** "gold-clean" Apache/MIT. Provenance is the best-documented of any model the harness uses.
- **Notes:** outputs are owned by the user. Re-evaluate the revenue gate if a game monetizes at
  scale. Keep any *music* (ACE-Step, future sub-stream) instrumental — vocal style-mimicry risk.

## Hardware

- **Machine / GPU:** ai2, gfx1201 (R9700), AMD ROCm. Generation of all four clips was fast
  (seconds each). Post step on the workstation.
- **Stack:** ComfyUI on ROCm. (First confirmed Stable Audio 3 run on this box.)

## Inputs

- **Prompts:** dense SFX descriptions in the blueprint's SFX style (source/material/space/time);
  see `SFX[]` in `generate_sfx.py`. Negative prompt empty.
- **Seeds:** 101–104 (one per clip).
- **Key params:** steps 50, cfg 7, sampler `lcm`, scheduler `simple`, denoise 1; length per clip
  via `EmptyLatentAudio.seconds` (1.5–12 s). Model emits **44.1 kHz** stereo FLAC (not the 48 kHz
  the card cites for the hosted model).

## Steps

1. `python3 prototypes/sfx/generate_sfx.py` → `outputs/*.flac` (queues each graph on `ai2:8188`).
2. Per clip: `python3 prototypes/optimize_audio.py <flac> [--loop] --lufs <tgt> [--cross <s>]`
   → `outputs/optimized/<name>.{ogg,wav}`.
3. DWA import: copy `thruster_loop.ogg → public/assets/sfx_thruster.ogg`; preload in BootScene;
   play/stop the looping sound from `Ship.updateThrusters` transit state.

## Result

- **Sample outputs:** [`samples-2026-06-23/`](samples-2026-06-23/) (`ui_click`, `impact_metal`,
  `thruster_loop`, `station_hum` — optimized `.ogg`).
- **What worked:** clean local generation; the ffmpeg post step normalizes to target loudness
  (measured loops: −18.35 / −21.86 LUFS vs −18 / −22 targets) and authors a **seam-free loop** via
  tail→head overlap-add. DWA `make compile` + `make build` pass; `sfx_thruster.ogg` bundles to
  `dist/assets/`. Thruster bed plays on transit, stops on arrival — pairs with the flame plume.
- **What failed / fixed during the run:** `loudnorm` silently upsamples to 192 kHz (pinned output
  `-ar` back to source); aggressive silence-trim gutted the click (loosened to −60 dB); `amix`
  emits PTS that crash `concat` (regenerate timestamps with `asetpts=N/SR/TB`). All resolved.

## Repeatability

- Deterministic given seed. Prompt style transfers well. Loudness/loop params are per-asset-class
  CLI flags. In-browser audio audition is the operator's (as with the flame visual).

## Next

- **lcm/50/cfg7** are the blueprint defaults; sweep steps/sampler for quality vs the (untested)
  hosted-style settings.
- Fold a small **SFX manifest** (name → seconds/seed/loop/lufs) so generate + optimize run from one
  source (currently `SFX[]` carries it; optimize is invoked per-file).
- **music sub-stream** via ACE-Step 1.5 (instrumental), and a Sounding (Bevy `bevy_audio`) import to
  pair with the deferred `bevy_hanabi` thruster.
- Consider downloading the non-base `stable_audio_3_medium` (instruct) checkpoint to compare.
