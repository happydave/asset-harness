# Track: pbr-materials

**Status:** 🟡 pipeline working — Z-Image albedo (`ai2`) + local clean derivation →
Bevy-ready sets. See [discover.md](discover.md) and the
[hull + ground findings](findings/2026-06-22-pbr-hull-and-ground.md). In-engine (Sounding)
verification pending.

## Purpose

Turn an AI-generated base color (albedo) into a full PBR material set — **normal**,
**roughness**, **ambient occlusion** (height optional) — for Sounding's 3D surfaces and
Scrapper's Soul's 2D lighting.

## Approach (to validate)

- Generate seamless base color in ComfyUI (shares tooling with the [2d](../2d/) track).
- Derive maps via a delight + material-estimation pass and/or DeepBump-style normal generation.
- Export as engine-ready textures (KTX2/PNG for Bevy).

High value and still essentially 2D generation, so this is the natural second track after 2d.

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
