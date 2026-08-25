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
| Checkpoints | **fp8_scaled** (`wan2.2_i2v_high/low_noise_14B_fp8_scaled`) — the default, no flag needed |
| LoRA | **both `lightx2v_4steps` LoRAs**, one per stage |
| Steps / cfg | 4 / **1** |
| Sampler / scheduler / shift | euler / simple / ModelSamplingSD3 **5** |
| Resolution / frames | 1280×720, 33 f @ 16 fps (≈2.06 s) |
| Cost | **~127 s/clip** |
| After render | interpolate the finished mp4 if it reads framey (`interpolate.py --fps 48`) |

**Prerequisite: `ai2`'s ComfyUI must run with `--disable-mmap`.** Without it a single checkpoint load
takes **35.8 min** instead of 6 s, and no dtype choice can rescue that (WI 1161). Check before a batch:

```bash
ssh ai2 'systemctl show comfyui.service -p ExecStart | grep -o -- --disable-mmap'
```

It is supplied by `/etc/systemd/system/comfyui.service.d/disable-mmap-workaround.conf`; if that file is
renamed `.disabled`, the flag is off. **Do not re-enable it unilaterally** — it is a shared service, and
it was switched off once for host-RAM pressure. fp8 halves that pressure (~33 GB vs ~69 GB), which is
part of why fp8 is the recipe.

```bash
python generate_clip.py --image horde_boulevard.png --out clip_horde \
  --prompt "<scene + gentle motion verbs — see 'Writing the prompt'>" \
  --width 1280 --height 720 --frames 33 --fps 16 --seed 301
```

**Take the recipe whole.** Its parts are interdependent — the 4-step LoRAs belong to the 4-step 2/2
split, and pulling one setting into a different configuration is how the earlier failures happened.

### VRAM and length

Only **one stage is resident at a time** — ComfyUI evicts the high-noise expert before loading the
low-noise one, at either dtype (WI 1161 measured this; the earlier guess that fp8 would keep both
resident is wrong). That is fine, because with `--disable-mmap` a reload costs 6 s. What matters is
that **fp8 fits without spilling** (20.0 of 32.6 GB, `loaded completely`) while **fp16 spills**
(`loaded partially`, ~1.8 GB offloaded, 33–36 lowvram patches) — which costs sampling throughput as
well as load time: the same two sampler steps take ~3 min under fp16 against 47 s under fp8.

Consequences:

- **Longer clips need lower resolution.** 6 s (97 f) **OOMs at 720p**; run 97 f at **832×480**.
- Restart ComfyUI before a big Wan run for a clean VRAM slate, and again afterwards before any batch of
  ACE-Step or Z-Image work — a lowvram/partial Wan job leaves the model manager evicting every job.

### Chaining clips into a longer continuous shot

Use **`chain_clip.py`** — it runs the whole loop and measures every seam:

```bash
python chain_clip.py --image start.png --links 3 --out flight \
  --width 1280 --height 720 --frames 97 \
  --prompt "the skiff glides forward over the cloud sea, mist drifting past"
```

It generates a link, extracts and cleans its last frame, generates the next link from that frame,
concats, and reports each seam's SSIM against the local adjacent-frame norm. Resumable: links already
on disk are reused.

**720p × 97 f works** (WI 1160) — the old 832×480 ceiling was an fp16 artifact, lifted by the move to
fp8. Cost is ~11 min per 6 s link at 720p; 832×480 is cheaper and remains the driver default.

The cleanup is a **content-preserving** ffmpeg pass (`unsharp`, plus optional `hqdn3d`) — it must sharpen
**without moving content**. Two rules learned the hard way:

- **Do not** use a low-denoise img2img or realifier to clean the frame. It restores more detail but
  shifts content, which breaks the seam.
- **Do not** apply a colour grade per seam. It compounds — a 3-link chain measured +9.6% saturation from
  a per-seam `eq=…:saturation=1.05`. `chain_clip.py` leaves the grade off by default for this reason.

i2v reproduces its start frame *approximately* (SSIM ~0.94, not 1.0), so the seam is content-continuous
rather than pixel-continuous — no positional jump, a faint acuity lift. A short crossfade hides it if
needed, but the shipped chains have used plain concat.

## The alternatives

**fp16 instead of fp8.** Same graph, `--fp16`. Delivered the July clips and is the higher-precision
reference, but **3.0× slower** (384 s vs 127 s), spills to lowvram, and needs ~69 GB of host RAM against
fp8's ~33 GB. fp8's cost is a marginal softness — slightly more haze, slightly less separation between
figures, SSIM 0.939 against fp16 on a crowd shot. **Reach for fp16 when a shot is precision-sensitive**
(a close subject where softness would read), not by default. Note the quality comparison was made on one
scene-scale shot; for character close-ups it is provisional.

**no-LoRA, 20-step.** From WIs 1018/1019, before the `wan2.2-test` config was adopted: `--no-lora`, 20
steps, cfg 3.5–5, shift 5, 81 f. Coherent motion, and the only path that **keeps negatives live** (see
below), but ~52–79 min/clip. Reach for it only if you specifically need cfg > 1.

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
