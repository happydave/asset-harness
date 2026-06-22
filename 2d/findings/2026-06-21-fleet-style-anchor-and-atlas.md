# Findings: fleet style-anchor + downstream atlas pipeline

**Date:** 2026-06-21
**Track:** 2d
**Verdict:** works

## Goal

Close the second half of the 2D harness: (1) prove a **style anchor** keeps a multi-ship
*fleet* visually coherent without LoRA/IPAdapter, and (2) build the **downstream** path that
turns raw RGBA renders into engine-ready output (trim → downscale → texture atlas) for the
DWA Phaser project.

## Tooling

- **Generation:** same clean stack as
  [the hauler finding](2026-06-21-dwa-hauler-zimage-controlnet.md) — Z-Image Turbo + Z-Image
  Fun ControlNet (Canny) + BiRefNet-HR-matting. All Apache/MIT.
- **Style anchor:** `run_zimage_controlnet.py` now splits prompt into a shared `STYLE` preamble
  + per-ship `subject`; `generate_fleet.py` applies `STYLE` + a **fixed seed** across all ships.
- **Downstream:** `build_atlas.py` (PIL only) — alpha-bbox trim, LANCZOS downscale to a target
  max dimension, shelf-pack, emit Phaser **JSON-Hash** atlas.

## Licensing

Unchanged from the hauler finding — entire chain Apache/MIT. **Effective output license: Apache 2.0.**
Safe for a clean/commercial pack: **yes**.

## Hardware

`ai2` (AMD R9700, gfx1201). Two 8-step generations back-to-back, no issues.

## Inputs

- **Shared STYLE:** "top-down orthographic game sprite, industrial used-future space vessel,
  weathered painted steel hull, gunmetal grey with rust-orange hazard accents, soft even studio
  lighting, clean readable silhouette, centered, isolated on a plain solid white background,
  crisp detailed concept art".
- **Subjects:** hauler (side cargo pods + 3 nozzles) and miner (forward drilling rig + 2 round
  ore tanks + twin nozzle). Distinct control primitives per ship.
- **Seed:** 729703840979498 (fixed for the fleet). ControlNet strength 0.85.

## Result

- **Style coherence: strong.** Both ships read as one faction — identical palette (gunmetal +
  rust-orange), lighting, and view — with clearly different silhouettes. Validates style anchor
  via prompt + fixed seed as sufficient (no LoRA/IPAdapter needed).
- **Atlas: valid.** `samples-2026-06-21-fleet/dwa_ships.png` (239×256 RGBA) +
  `dwa_ships.json` (Phaser JSON-Hash, frames `hauler` 97×256, `miner` 140×256). Standalone
  trimmed sprites also emitted (`hauler.png`, `miner.png`).

## Repeatability

Deterministic; `generate_fleet.py` writes a `fleet_manifest.json` (style, seed, per-ship prompt
+ rgba); `build_atlas.py` is pure and re-runnable.

## Known limitation

`build_atlas.py` normalizes **each** sprite to `--max-dim`, so inter-ship *relative* scale is
lost (the miner and hauler are both 256 tall here). For a fleet where a miner should be visibly
smaller than a hauler, generate at a consistent px-per-unit or pass per-ship target sizes.
Captured as a next step, not a blocker.

## DWA import recipe (thin, belongs in a DWA work item)

DWA currently builds all art programmatically via `Graphics.generateTexture(KEY, w, h)` (e.g.
`SHIP_TEXTURE_KEY` in `src/entities/Ship.ts`) and loads **no** external assets. To use the
atlas instead:

1. **Place files** in DWA's Vite public dir: `public/assets/dwa_ships.png` + `dwa_ships.json`
   (served at URL `assets/dwa_ships.*`).
2. **Preload** in `src/scenes/BootScene.ts`:
   `this.load.atlas('dwa_ships', 'assets/dwa_ships.png', 'assets/dwa_ships.json')`.
3. **Use the frame** where the ship sprite is created — texture key `'dwa_ships'`, frame
   `'hauler'` — replacing the `generateTexture` path (keep it as a fallback if desired).
4. **Mind two details:** (a) physics body size now follows the sprite's pixel size — set it
   explicitly; (b) sprites are drawn **nose-up**, while Phaser angle 0 faces right — apply a
   −90° render offset (or `setAngle`) so heading matches motion.

This edit changes the DWA repo, so it should be a DWA SideQuest/work item, not part of
asset-harness (per the project's engine-agnostic boundary).

## Next

- Preserve inter-ship relative scale (per-ship target sizes / consistent px-per-unit).
- Add more fleet members (tug, scout) to stress style coherence further.
- Generalize beyond ships: station/base modules (the DWA modular-components need).
- Execute the DWA import as a scoped change and verify in-game.
