---
name: prompting-z-image
description: Use when writing a text-to-image prompt or picking model/steps/cfg for a Z-Image still in ComfyUI — opaque i2v seed frames or standalone storytelling stills.
---

# Prompting Z-Image

## Overview

Z-Image (Tongyi, Lumina2 lineage) is a text-to-image model with a large Qwen-3-4B text encoder, so it
follows natural-language, compositional prompts well. Here it produces **opaque full-scene stills** — the
seed frames for [`prompting-wan-i2v`](../prompting-wan-i2v/SKILL.md), or standalone stills.

## Recipe

| Setting | Value |
|---|---|
| Model | `base` (best for storytelling; `zanime` for illustrated) |
| Steps / cfg | 20 / 4.0 (raise toward 28–40 if a still looks undercooked) |
| Sampler / shift | euler / simple, ModelSamplingAuraFlow shift 3.0 |
| Encoder / VAE | `qwen_3_4b` (type `lumina2`) / `ae` |
| Output | opaque RGB — **no ControlNet, no matte tail** |

Stills cost seconds — generate several and pick. Avoid Turbo for hero stills (lower quality, and it
ignores negatives + shows almost no seed-to-seed variation).

## Writing the prompt

- Write **natural-language sentences** (subject → setting → style/lighting/mood), not tag soup. The
  encoder rewards specificity and coherent description.
- Lead with the subject that must be right; put style/lighting after.
- For an i2v seed still, **describe a rich full scene** — it's the whole frame Wan animates, not a sprite.
- Keep it **opaque**: no alpha. A matted/RGBA still makes Wan invent a background and hallucinate text.

## Negatives

Use a defect + unwanted-text guard (`blurry, jpeg artifacts, watermark, text, caption, title, ui,
deformed, extra limbs, bad anatomy`). **Do not** negate "cluttered/busy background" for an establishing
shot — it wants richness. Negatives work on `base` (real CFG); Turbo ignores them.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| Booru/tag-soup prompting | Natural-language sentences |
| Negating "cluttered background" for an establishing shot | Leave it out; describe fullness positively |
| Turbo for hero stills | `base`; Turbo is a speed fallback only |
| Matted / RGBA output for i2v | Opaque RGB full scene |
| Still looks flat/undercooked | Raise steps toward 28–40 before other changes |

## Explicit AI freedom

Choose composition, lighting, and style wording; `base` vs `zanime`; resolution/aspect; seed; and how
many candidates to generate — no need to ask.

## Source

Preset and traps: `../../music-video/prototypes/generate_still.py` and the music-video Wan-quality
findings entry. Prompt hygiene: `../../music-video/license-lane.md`.
