# Track: 2d

**Status:** 🟡 in progress — generate→atlas pipeline working end-to-end on the clean stack.
Discovery complete; [single sprite](findings/2026-06-21-dwa-hauler-zimage-controlnet.md) and a
[style-coherent fleet + Phaser atlas](findings/2026-06-21-fleet-style-anchor-and-atlas.md)
validated (Z-Image + Fun ControlNet + BiRefNet, all Apache/MIT, on `ai2` gfx1201). Remaining:
preserve inter-ship scale, station/base modules, and the (DWA-side) in-game import.

## Purpose

Repeatable generation of 2D, game-ready raster assets:

- **Sprites with clean alpha** — ships, units, props, asteroids, nets (DWA; Scrapper's Soul).
- **Tiling textures** — seamless ground/material tiles.
- **Backdrops / skyboxes** — large static backgrounds, equirectangular panoramas, planet/LOD art.

This is the first track because 2D generation is the most mature, the feedback loop is
minutes, and it lets us validate the *whole harness shape* (spec → generate → post-process →
engine-ready output + provenance) at lowest risk.

## Target outputs

- PNG with premultiplied/straight alpha, trimmed.
- Packed texture atlas + JSON (Phaser/Ebitengine consumable).
- Seamless tiles verified by edge-wrap inspection.

## The hard problem: style coherence

Individually-nice assets that don't share a visual language look worse than mediocre hand art.
Each consuming game needs a **style anchor** (LoRA / fixed reference set via IPAdapter / locked
palette / reused workflow + seed discipline) that every asset passes through. Validating an
anchor approach is an explicit goal of this track, not an afterthought.

## Plan of attack

1. **Discovery** — pick base model (SDXL vs Flux), confirm it runs locally, survey
   alpha/background-removal (rembg, SAM) and atlas packing options.
2. **Prototype** — one DWA hauler end-to-end: concept → consistent top-down angle (ControlNet
   from a posed primitive) → clean alpha → atlas → rendered in Phaser. Capture in `findings/`.
3. **Harness** — fold the working path into a parameterized Python script + ComfyUI API
   workflow; document it here and flip status to 🟢.

## Contents

- [`discover.md`](discover.md) — generation-stack discovery: installed models on `ai2`,
  **license matrix** (clean engine = Z-Image Turbo; FLUX.2 Klein 9B is non-commercial), and
  remaining gaps. **Read this first.**
- `findings/` — one filled-in copy of [`../_template/findings.md`](../_template/findings.md)
  per experiment.
- `prototypes/` — workflows, scripts, and representative sample outputs.
