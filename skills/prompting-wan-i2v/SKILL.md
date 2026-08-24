---
name: prompting-wan-i2v
description: Use when writing a motion prompt or picking a config for a Wan2.2 image-to-video (i2v-A14B) clip in ComfyUI — animating a still into a short shot on ai2.
---

# Prompting Wan2.2 i2v

## Overview

Wan2.2 i2v-A14B is a **two-stage mixture-of-experts** model — a high-noise checkpoint that carries
structure and motion, and a low-noise checkpoint that carries detail — which animates a still you
provide. The still is frame 0, so the prompt describes what *changes*, not what is already there.

**Both experts are required.** Running one across the whole schedule is off-distribution and the clip
wanders: figures pop in, scenes morph, night drifts to day. This was tried and abandoned
(`generate_clip_single.py`, kept only as a record).

## Recipe — use this one

Replicates ai2's saved `wan2.2-test` workflow, built by `generate_clip.py --fp16`. This is the config
that produced the delivered motion clips (2026-07-28, clamor-motion session).

| Setting | Value |
|---|---|
| Stages | **both** — high-noise steps 0→2, latent handed to low-noise for 2→4 |
| Checkpoints | **fp16** (`wan2.2_i2v_high/low_noise_14B_fp16`) |
| LoRA | **both `lightx2v_4steps` LoRAs**, one per stage |
| Steps / cfg | 4 / **1** |
| Sampler / scheduler / shift | euler / simple / ModelSamplingSD3 **5** |
| Resolution / frames | 1280×720, 33 f @ 16 fps (≈2.06 s) |
| Cost | ~6–10 min/clip (fp16 loads dominate) |
| After render | interpolate the finished mp4 if it reads framey (`interpolate.py --fps 48`) |

```bash
python generate_clip.py --fp16 --image horde_boulevard.png --out clip_horde \
  --prompt "<scene + gentle motion verbs — see 'Writing the prompt'>" \
  --width 1280 --height 720 --frames 33 --fps 16 --seed 301
```

**Take the recipe whole.** Its parts are interdependent — the 4-step LoRAs belong to the 4-step 2/2
split, and pulling one setting into a different configuration is how the earlier failures happened.

### VRAM and length

The 2/2 split is what makes this affordable: only **one 28 GB model is resident at a time** (one swap
per clip, not one per sampling step), peaking ~33.5 of 34 GB. Consequences:

- **Longer clips need lower resolution.** 6 s (97 f) **OOMs at 720p**; run 97 f at **832×480**.
- Restart ComfyUI before a big Wan run for a clean VRAM slate, and again afterwards before any batch of
  ACE-Step or Z-Image work — a lowvram/partial Wan job leaves the model manager evicting every job.

### Chaining clips into a longer continuous shot

Proven on a 12 s skiff flight (lantern-crossing, 2026-07-29):

1. Generate clip 1 (97 f, 832×480).
2. Extract its last frame; clean it with a **content-preserving** ffmpeg pass — `hqdn3d` light denoise
   + moderate `unsharp` luma + slight contrast/saturation. It must sharpen **without moving content**.
3. Generate clip 2 from the cleaned frame, prompt continuing the motion.
4. Concat, with a short crossfade over the seam.

i2v reproduces its start frame at frame 0, so clip 2 opens on (approximately) clip 1's last frame and
the seam is content-continuous. **Do not** use a low-denoise img2img to clean the frame — it restores
more detail but shifts content, which breaks the seam.

## The alternative recipe — fp8, no-LoRA, 20-step

From WIs 1018/1019, before the `wan2.2-test` config was adopted: fp8 checkpoints, `--no-lora`, 20 steps,
euler/simple, cfg 3.5–5, shift 5, 81 f @ 16 fps, 1280×720 (fits fp8 with no spill). It produces coherent
motion and **keeps negatives live** (see below), but costs **~52–79 min/clip**.

Reach for it only if you specifically need cfg > 1. Otherwise the production recipe is both better
validated and several times faster.

## Writing the prompt

- **Describe the scene with gentle motion verbs** — "zombies slowly stumbling", "mist churning" — rather
  than camera-move language. *(Reported from the clamor-motion session; the evidence that camera-heavy
  prompts drive drift comes from its single-stage runs, so treat this as a working preference for the
  two-stage path, not a tested result there.)*
- One primary motion per shot.
- Keep the start image **opaque RGB** — alpha makes Wan invent a background and hallucinate text.
- **Anchor** what stays still ("face still, only the hair moves"). Don't re-describe the static scene;
  aim ~80–120 words.
- A motion clip is an **accent**. Most shots are stills with Ken Burns; constant motion reads as noise.
- **Never place a clip immediately before or after its own source still** in a cut — the still reads as
  a freeze of the shot that just played.

## Negatives

Keep the stock Chinese+English negative in `generate_clip.py` verbatim (the Wan authors' own). Negatives
only take effect at **cfg > 1**, so at the production recipe's **cfg 1 they are inert** — the 2/2 expert
split and the start image are doing the work instead. If you genuinely need negative steering, that is
the one reason to fall back to the no-LoRA path above.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| Running a single expert to dodge the model swap | Both stages, 2/2 split — one expert wanders or barely moves |
| Mixing settings between the two recipes | Take one recipe whole; the LoRAs belong to the 4-step split |
| 6 s clip at 720p | OOMs — drop to 832×480 for 97 f |
| Expecting negatives to steer at cfg 1 | They are inert; use the no-LoRA recipe if you need them |
| RGBA / matted start image | Opaque RGB only |
| Describing the scene already in the image | Describe what changes |
| Animating every shot | Motion is an accent; most shots are Ken Burns stills |
| Framey playback | Interpolate the finished clip, not a settings problem |
| A batch of stills crawling right after a Wan job | Restart ComfyUI — the model manager is evicting every job |

## Community notes (reported, not fact)

Shift trades motion for calm: the 5.0 default favors motion; **raise toward 8–9 if a shot is too busy or
unstable.** If a clip ignores its start image entirely, that's a known bug — sanity-check plain i2v at
defaults, not the prompt. Community reports corroborating "the 4-step LoRA kills motion" were collected
against the no-LoRA path; they do not describe the 2/2 split this skill now recommends.

## Explicit AI freedom

Choose the subject motion, whether a shot earns a clip vs a Ken Burns still, seed, and frame count
within the VRAM limits above — no need to ask.

## Source

Production recipe, chaining, and VRAM behaviour:
`../../music-video/findings/2026-08-24-production-sessions.md` and the session notes it cites. Earlier
spike results (no-LoRA path, interpolation): `../../music-video/findings/` Wan i2v quality +
settings/interpolation entries. Code: `../../music-video/prototypes/generate_clip.py`,
`../../music-video/prototypes/interpolate.py`. Prompt hygiene: `../../music-video/license-lane.md`.
