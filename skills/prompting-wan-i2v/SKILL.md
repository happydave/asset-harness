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

`generate_clip.py` builds this with no flags except the frame count: its default is still 33, so a
shot with motion passes `--frames 81`. The 4-step LoRAs belong to the 4-step 2/2 split; mixing
settings between recipes is how earlier runs failed.

| Setting | Value |
|---|---|
| Stages | both — high-noise steps 0→2, low-noise 2→4 |
| Checkpoints | `wan2.2_i2v_high/low_noise_14B_fp8_scaled` |
| LoRA | both `lightx2v_4steps` LoRAs, one per stage |
| Steps / cfg | 4 / 1 |
| Sampler / scheduler / shift | euler / simple / 5 |
| Resolution / frames | 1280×720 @ 16 fps: **81 f (≈5 s) for any shot with motion** — Wan 2.2 is trained and shipped at 81 f; 33 f (≈2 s) only for a micro-accent (a blink, a flicker) |
| Cost | 33 f ~127 s; 97 f 791 s (both measured on `ai2`); 81 f not measured — budget ~10 min, not the 2.5× a linear guess gives |
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

The gates were calibrated on 97-frame links, not on the 33-frame single clip, so moving single clips
to 81 f leaves them as they are. Each gate compares a seam with the 8 frames before it, not with the
link length. What link length does change is the seam count: 81-frame links put 20% more seams in a
minute than 97-frame links, and each seam is one more cleanup pass, which is the part that compounds.
Keep links at 97 f unless a measurement says otherwise.

## Alternatives

- **`--fp16`** — precision-sensitive shots only (a close subject where softness would read). 3×
  slower, spills to lowvram, ~69 GB host RAM.
- **`--no-lora`** — 20 steps, cfg 3.5–5; negatives act on every step; ~1 h per clip. The only
  negatives-live path the scripts build today; the three-sampler split (Negatives) is the cheap one.
- **A camera variant** — `Wan2.2-Fun-A14B-Control-Camera` takes pan/zoom/rotate/static codes through
  `WanCameraEmbedding`, independent of the prompt, and works with the 4-step LoRA. Reported weak on
  illustration-style input; not run here.

## Writing the prompt

- **On this recipe**, gentle motion verbs ("mist churning", "figures slowly stumbling"), not camera
  moves. That is a property of the recipe, not of Wan 2.2: the 4-step LoRA on the high-noise expert
  (the stage that carries global motion) suppresses motion, and 33 f is too short for a move to read.
  Wan 2.2 does take camera direction, seed-dependently. For a camera move use 81 f and the
  three-sampler split, a camera variant (Alternatives), or a depth-driven pass that invents nothing.
- Phrase a camera move as its **destination**, last in the prompt: "pans left to the fireplace", not
  "pans left". Wan guides and Lightricks' camera-LoRA cards converge on this.
- One primary motion per shot. Anchor what stays still ("face still, only the hair moves"). ~80–120
  words; describe what changes, not the scene already in the image.
- Start image is opaque RGB. Alpha makes Wan invent a background and hallucinate title text.
- A clip is an accent: most shots are Ken Burns stills. Never place a clip next to its own source still.

## Negatives

Keep the stock negative in `generate_clip.py` verbatim. At cfg 1 negatives are inert, and this
recipe runs every step at cfg 1.

The **three-sampler split** makes them live for a few tens of seconds, not an hour: high-noise with
*no* speed LoRA at cfg ~3.5 for 1–2 steps, then high-noise + speed LoRA at cfg 1, then low-noise +
speed LoRA at cfg 1. It also restores the motion the distill suppresses. Reported (WanGP's LoRA
guide; lightx2v's Wan2.2-Lightning discussion #26), not measured here, and `generate_clip.py` does
not build it yet.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| One expert to dodge the model swap | Both stages, 2/2 split |
| Mixing settings between recipes | Take one recipe whole |
| RGBA / matted start image | Opaque RGB only |
| A camera move on the 4-step recipe at 33 f | 81 f plus the three-sampler split, a camera variant, or a depth pass |
| Stills crawling after a Wan job | Restart ComfyUI |

## Community notes (reported, not fact)

Shift trades motion for calm — raise toward 8–9 if a shot is too busy. A clip that ignores its start
image is a known bug, not a prompt problem.

## Explicit AI freedom

Subject motion, which shots earn a clip, seed, and frame count within the limits above.

## Source

`../../music-video/findings/2026-08-24-production-sessions.md`,
`2026-08-25-wan-fp8-vs-fp16-and-the-mmap-flag.md`, `2026-08-25-clip-chaining.md`; the camera, frame-count
and three-sampler corrections from WI 1591 round 5 (tickets
`docs/projects/asset-harness/research/web-research-wan-camera-scenes.md`); code
`../../music-video/prototypes/generate_clip.py`, `chain_clip.py`; hygiene `../../music-video/license-lane.md`.
