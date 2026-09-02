---
name: prompting-wan-i2v
description: Use when writing a motion prompt or picking a config for a Wan2.2 image-to-video (i2v-A14B) clip in ComfyUI — animating a still into a short shot on ai2.
---

# Prompting Wan2.2 i2v

## Overview

Wan2.2 i2v-A14B is a two-stage mixture-of-experts model: a high-noise expert carries structure and
motion, a low-noise expert carries detail. The still is frame 0, so the prompt describes what *changes*.
**Both experts are required** — one alone wanders (pop-ins, morphing, night drifting to day).

## Recipe — take it whole

`generate_clip.py` builds this with no flags. The 4-step LoRAs belong to the 4-step 2/2 split; mixing
settings between recipes is how earlier runs failed.

| Setting | Value |
|---|---|
| Stages | both — high-noise steps 0→2, low-noise 2→4 |
| Checkpoints | `wan2.2_i2v_high/low_noise_14B_fp8_scaled` |
| LoRA | both `lightx2v_4steps` LoRAs, one per stage |
| Steps / cfg | 4 / 1 |
| Sampler / scheduler / shift | euler / simple / 5 |
| Resolution / frames | 1280×720, 33 f @ 16 fps (≈2 s) |
| Cost | ~127 s per clip |
| If framey | `interpolate.py --fps 48` on the finished mp4 |

```bash
python generate_clip.py --image still.png --out clip_name --seed 301 \
  --prompt "<scene + one gentle motion — see Writing the prompt>"
```

### Before a batch

- `ai2` must run ComfyUI with `--disable-mmap` (a checkpoint load is 6 s with it, 36 min without).
  Check: `ssh ai2 'systemctl show comfyui.service -p ExecStart | grep -o -- --disable-mmap'`. Shared
  service — report a missing flag, do not change the config.
- Restart ComfyUI before a big Wan run, and again before any ACE-Step or Z-Image batch that follows
  one: a Wan job leaves the model manager evicting every job.

### Longer shots

`chain_clip.py` chains links (generate → clean the last frame → generate from it → concat), measures
every seam, and resumes. 720p × 97 f works; 832×480 is the cheaper default. The per-seam cleanup
compounds, so it stays near identity: **no sharpen, no colour grade, no img2img or realifier** on a
seam frame. Gates: continuity (SSIM within 0.05 of the local norm) and acuity (±10%).

## Alternatives

- **`--fp16`** — precision-sensitive shots only (a close subject where softness would read). 3×
  slower, spills to lowvram, ~69 GB host RAM.
- **`--no-lora`** — 20 steps, cfg 3.5–5; the only path where negatives act; ~1 h per clip.

## Writing the prompt

- Gentle motion verbs ("mist churning", "figures slowly stumbling"), not camera moves.
- One primary motion per shot. Anchor what stays still ("face still, only the hair moves"). ~80–120
  words; describe what changes, not the scene already in the image.
- Start image is opaque RGB. Alpha makes Wan invent a background and hallucinate title text.
- A clip is an accent: most shots are Ken Burns stills. Never place a clip next to its own source still.

## Negatives

Keep the stock negative in `generate_clip.py` verbatim. At cfg 1 negatives are inert; if you need
them, use `--no-lora`.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| One expert to dodge the model swap | Both stages, 2/2 split |
| Mixing settings between recipes | Take one recipe whole |
| RGBA / matted start image | Opaque RGB only |
| Stills crawling after a Wan job | Restart ComfyUI |

## Community notes (reported, not fact)

Shift trades motion for calm — raise toward 8–9 if a shot is too busy. A clip that ignores its start
image is a known bug, not a prompt problem.

## Explicit AI freedom

Subject motion, which shots earn a clip, seed, and frame count within the limits above.

## Source

`../../music-video/findings/2026-08-24-production-sessions.md`,
`2026-08-25-wan-fp8-vs-fp16-and-the-mmap-flag.md`, `2026-08-25-clip-chaining.md`; code
`../../music-video/prototypes/generate_clip.py`, `chain_clip.py`; hygiene `../../music-video/license-lane.md`.
