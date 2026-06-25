# Track: audio

**Status:** 🟢 both sub-streams working. **SFX** via Stable Audio 3 (incl. the DWA thruster
start/burn/stop set); **ambient music** via ACE-Step 1.5 (instrumental loop beds). Shared ffmpeg
post (normalize / seamless loop / ogg+wav). See [discover.md](discover.md) and findings:
[SFX](findings/2026-06-23-sfx-stable-audio-3.md) ·
[thruster set](findings/2026-06-24-thruster-set.md) ·
[ambient music](findings/2026-06-24-ambient-music-ace-step.md).

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
