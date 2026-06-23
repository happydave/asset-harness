# Findings: DWA celestial bodies — planet + per-resource asteroids

**Date:** 2026-06-22
**Track:** 2d
**Verdict:** works

## Goal

Extend the 2D harness to **celestial bodies** for DWA: a rotating gas-giant planet and a set
of per-resource asteroid sprites (+ an "unknown" variant for scan-gating). These unblock DWA
work items 584 (planet sprite + rotation) and 585 (asteroid sprites); 586 (scan-gate) uses the
`unknown` frame.

## Tooling

- Same clean stack as the fleet (Z-Image Turbo + Z-Image Fun ControlNet Canny + BiRefNet
  matting; all Apache/MIT).
- `make_celestial.py` — PIL control primitives: a **planet** disc with concentric band arcs and
  a deliberately **off-centre** storm (rotation only reads on an asymmetric feature), and three
  distinct angular **rock** silhouettes with internal facet edges.
- `generate_celestial.py` — a **celestial-neutral** STYLE anchor (keeps the clean-cutout
  framing/lighting/white-bg the matting depends on; drops the vessel/steel-hull specifics from
  the fleet anchor) + per-subject prompts. Seed **family** off the fleet base
  (729703840979498 +0..+5) for set coherence with per-asteroid offset so repeated rock
  primitives still vary.
- `build_atlas.py` (default trim+downscale mode) → `dwa_planet` (1×512px) and `dwa_asteroids`
  (5 frames @256px: iron/ice/silicates/rare-metals/unknown).

## Licensing

Unchanged — entire chain Apache/MIT. **Effective output license: Apache 2.0.** Clean-pack safe.

## Hardware

`ai2` (AMD R9700, gfx1201), ComfyUI 0.22.0. Six 8-step generations, no issues.

## Inputs

- **Style anchor:** "top-down orthographic game sprite, science-fiction celestial body, soft
  even lighting, clean readable silhouette, centered, isolated on a plain solid white
  background, crisp detailed concept art."
- **Strength:** planet 0.85, asteroids 0.8. **Seeds:** 729703840979498 (planet) + 1..5.

## Result

- **Planet:** recognizable pole-on gas giant, concentric bands + an off-centre storm (upper
  right) — the asymmetry needed for the in-engine z-rotation to read. Came out **dark/low
  contrast**; fine on the black space background but a brighter/larger pass is a possible redo.
- **Asteroids:** five **style-coherent, per-resource-distinct** sprites — iron (rust-orange
  veins), ice (translucent pale blue), silicates (tan/gold stone), rare-metals (dark + glowing
  violet veins), unknown (nondescript grey cratered rock). Canny at 0.8 produced a faceted
  "cut-mineral" look (more crystalline than rough) — consistent and readable, but a lower
  strength or rougher primitives would give a more weathered rock if desired.

## Repeatability

Deterministic (fixed seed family); manifests + per-run graphs saved. `make_celestial` and
`build_atlas` are pure/re-runnable.

## Known limitations / next

- Planet is dark; consider a brighter, higher-contrast re-roll or a second variant.
- Asteroids read as faceted gems; lower ControlNet strength (~0.6) or noisier primitives would
  soften them toward rough rock if that's preferred.
- No depletion/cracked variants (DWA scales sprites down on depletion — adequate for now).
- DWA-side imports are separate work items (584 planet, 585 asteroids).
