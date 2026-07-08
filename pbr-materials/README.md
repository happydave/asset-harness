# Track: pbr-materials

**Status:** 🟢 pipeline working + imported in-engine — Z-Image albedo (`ai2`) + local clean
derivation → Bevy-ready sets. See [discover.md](discover.md), the
[hull + ground findings](findings/2026-06-22-pbr-hull-and-ground.md), the
[structural-material library](findings/2026-06-25-structural-material-library.md) (4 structural +
3 surface sets; the structural four wired into Sounding WI 624), and the
[biome terrain library](findings/2026-07-07-terrain-library.md) (10 tileable terrain sets for
Sounding's biome layer, WI 871 — adds `tone_balance` hue anchoring + a multi-scale tiling audit).

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
