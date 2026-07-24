---
name: prompting-wan-i2v
description: Use when writing a motion prompt or picking steps/sampler/resolution for a Wan2.2 image-to-video (i2v-A14B) clip in ComfyUI — animating a still into a short hero shot on ai2.
---

# Prompting Wan2.2 i2v

## Overview

Wan2.2 i2v-A14B is a two-stage image-to-video model (high-noise checkpoint then low-noise) that animates
a still you provide. The still is frame 0 — the prompt describes what *changes*, not what is already
there.

## Recipe

| Setting | Value |
|---|---|
| LoRA | **none** (`--no-lora`) — see the rule below |
| Resolution | 1280×720 (fits fp8, no spill) |
| Steps / sampler | 20, euler / simple |
| CFG / shift | 3.5–5 / 5.0 (lower shift = more motion) |
| Frames / fps | 81 @ 16 fps (≈ 5 s) |
| After render | **interpolate to 48 fps** (`interpolate.py --fps 48`) — fixes the framey look |

Model load is once per session — batch shots. More steps or fancier samplers give only marginal gains;
keep 20 and use `--sampler/--scheduler` only to rescue a specific shot.

```bash
# 1. render (opaque RGB still in; --no-lora keeps motion)
python generate_clip.py --image survivor_dusk.png --out clip_survivor \
  --prompt "<motion + camera — see 'Writing the prompt'>" \
  --no-lora --steps 20 --cfg 4 --shift 5 \
  --width 1280 --height 720 --frames 81 --fps 16 --seed 901
# 2. interpolate the finished mp4 to 48 fps
python interpolate.py clip_survivor.mp4 --out clip_survivor_48.mp4 --fps 48
```

`--image` and `--prompt` are required; run `generate_clip.py --help` for the rest.

## The one critical rule

**The 4-step lightx2v LoRA kills motion** (near-static or swirling output). Use `--no-lora` (20 steps)
for any shot where motion matters. Reach for the LoRA only when you want speed and don't care about
movement.

## Writing the prompt

- Describe **subject motion** and **camera move** (push-in, pan, tilt, dolly, orbit) in **separate
  clauses**; one primary motion per shot. Wan2.2 follows film-grammar terms well.
- Keep the start image **opaque RGB** — alpha makes Wan invent a background and hallucinate text.
- **Anchor** what stays still ("face still, only the hair moves"). Don't re-describe the static scene;
  aim ~80–120 words.
- A Wan clip is a **hero-shot garnish** — most shots are stills + Ken Burns; constant motion reads as
  noise.

## Negatives

Keep the stock Chinese+English negative in `generate_clip.py` verbatim (the Wan authors' own). Negatives
only take effect at **CFG > 1**, so the no-LoRA path is what keeps them live.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| 4-step LoRA on a shot that needs movement | `--no-lora` 20-step; the LoRA is a motion-killer |
| Chasing quality with 30 steps / fancy sampler | Marginal gain; keep 20, interpolate for smoothness |
| RGBA / matted start image | Opaque RGB only |
| Describing the scene already in the image | Describe motion + camera only |
| Animating every shot | Hero-shot garnish; most shots are Ken Burns stills |
| Framey playback | Interpolate the finished clip, not a settings problem |

## Community notes (reported, not fact)

Community reports corroborate no-LoRA (vendor claims the LoRA keeps motion; practitioners report it
doesn't). Shift trades motion for calm: the 5.0 default already favors motion; **raise toward 8–9 if a
shot is too busy or unstable.** If a clip ignores its start image entirely, that's a known bug —
sanity-check plain i2v at defaults, not the prompt.

## Explicit AI freedom

Choose the subject motion and camera move, whether a shot earns a clip vs a Ken Burns still, cfg within
3.5–5, seed, and frame count — no need to ask.

## Source

Recipe and traps from the music-video track: `../../music-video/prototypes/generate_clip.py`,
`../../music-video/prototypes/interpolate.py`, and `../../music-video/findings/` (Wan i2v quality +
settings/interpolation entries). Prompt hygiene: `../../music-video/license-lane.md`.
