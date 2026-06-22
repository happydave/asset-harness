# Findings: DWA station modules — grid/slot kit

**Date:** 2026-06-21
**Track:** 2d
**Verdict:** works

## Goal

Extend the 2D harness to **modular base/station components** for DWA, using a **grid/slot kit**
model (chosen over free-composition / whole-base images): square-cell modules with connection
ports on their edges that mate edge-to-edge when tiled, all coherent with the existing ship
style.

## Tooling

- Same clean stack (Z-Image Turbo + Z-Image Fun ControlNet + BiRefNet, all Apache/MIT).
- `make_modules.py` — square 1024 cell primitives with **ports centered on active edges at
  identical positions**, plus per-type interiors (hub/tank/habitat/solar/dock).
- `generate_modules.py` — module-specific STYLE preamble (shares the ship palette) + the fleet
  seed; ControlNet strength **0.9** to keep the footprint/ports locked.
- `build_atlas.py --cell N` — new **grid mode**: keeps the full square cell (no alpha-bbox trim,
  so ports stay aligned), uniform NxN frames, grid-packed. (Default trim+downscale mode is
  unchanged for free-standing sprites like ships.)
- `compose_base.py` — verification: tiles the cell sprites edge-to-edge, rotating each so its
  ports face the hub.

## Licensing

Unchanged — entire chain Apache/MIT. **Effective output license: Apache 2.0.** Clean-pack safe.

## Hardware

`ai2` (AMD R9700, gfx1201). Five 8-step generations, no issues.

## Inputs

- **Module STYLE:** "...modular space station component, square form factor, mechanical docking
  ports centered on the connecting edges..." + shared gunmetal/rust-orange palette.
- **Seed:** 729703840979498 (shared with the fleet). **Strength:** 0.9.
- **Modules + ports:** hub (4 edges), tank (N/S pass-through), habitat (N/S), solar (S end-cap),
  dock (S; external berthing ring).

## Result

- **All five modules are style-coherent** with each other and with the ship fleet.
- **Ports mate.** `samples-2026-06-21-station/base_layout.png` composes hub + solar (top) +
  habitat (right) + tank (left) + dock (bottom) into one station; connectors line up at the
  shared cell edges. This validates the grid/slot kit end-to-end.
- **Atlas:** `dwa_station.png` (808×160, five 160×160 cells) + `dwa_station.json` (Phaser
  JSON-Hash); standalone cell sprites also emitted.

## Repeatability

Deterministic (fixed seed); manifest + saved graphs per run; `build_atlas --cell` and
`compose_base` are pure/re-runnable.

## Known limitations

- **Rotation lives in the demo, not the data.** `compose_base.py` rotates modules to face the
  hub; in-engine, the game (or a layout descriptor) must apply the same rotation. A future step
  could bake a small "ports" manifest (which edges connect) per module.
- Larger stations need more module types (junction/elbow, airlock, greenhouse) — easy to add to
  `make_modules.py`.
- Per-module health/damage states, and an in-engine DWA `Base` that renders a composed station,
  are follow-ups (a DWA-side work item, like the ship import).

## Next

- Add a per-module **ports manifest** (connectable edges) so layout/rotation is data-driven.
- More module types; multi-cell (2×1) modules.
- DWA-side: render the composed station in the `Base` entity (separate work item).
