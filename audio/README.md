# Track: audio

**Status:** 🟡 SFX prototype done — Stable Audio 3 generate script + ffmpeg post (normalize /
seamless loop / ogg+wav); thruster loop imported into DWA. See [discover.md](discover.md) and the
[SFX findings](findings/2026-06-23-sfx-stable-audio-3.md). Music (ACE-Step, instrumental) next.

- **SFX** → **Stable Audio 3 Medium** (Stability Community License; fully-licensed training data;
  48 kHz; native SFX). Revenue-gated <$1M + bundles T5Gemma/Gemma terms — record in the gen log.
- **Music/ambient** → **ACE-Step 1.5** (**MIT**; runs on AMD). Instrumental/ambient only for shipped
  assets (vocal style-mimicry exposure).

## Purpose

Sound effects and music/ambient beds for DWA, Sounding, and Scrapper's Soul.

## Approach

- **Generate** with AI (ComfyUI native blueprints on `ai2`).
- **Post** with ffmpeg: EBU R128 normalize, trim, fades, author loop points, encode to `.ogg`
  (Phaser/web) and `.ogg`/`.wav` (Bevy `bevy_audio`).
- Track **model, weights license, training-data provenance, and per-output license** in the gen log.

## Contents

- `prototypes/{sfx,music}`, `findings/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
