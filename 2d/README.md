# Track: 2d

**Status:** 🟢 generate→atlas pipeline working end-to-end on the clean stack (Z-Image + Fun
ControlNet + BiRefNet, all Apache/MIT, on `ai2` gfx1201). Validated:
[single sprite](findings/2026-06-21-dwa-hauler-zimage-controlnet.md),
[style-coherent fleet + atlas](findings/2026-06-21-fleet-style-anchor-and-atlas.md), and a
[grid/slot station-module kit](findings/2026-06-21-station-modules-grid-kit.md) whose ports
tile, and a [radially-symmetric spider-miner body](findings/2026-07-03-dwa-spider-miner.md) for
DWA WI 813. The hauler now renders **in-game in DWA**. Remaining polish: data-driven
port/rotation manifest, more module types, and the DWA-side composed-base render.

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
- `prototypes/` — workflows, scripts, and representative sample outputs. Run
  `python3 prototypes/test_build_atlas.py` to regression-check the atlas post-processing
  (trim / alpha-threshold / packing; stdlib + PIL, no pytest, exits non-zero on failure).
