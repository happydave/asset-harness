# Findings: motor + battery parts, delight-refreshed solar surfaces

**Date:** 2026-06-25
**Track:** mechanical-kit
**Verdict:** works — 2 new parts + 4 refreshed surfaces, for Sounding WI 653

## Goal

Close the rover device gaps for Sounding WI 653 ("visible rover part assets"): the catalog had
`suspension`/`fuel_tank`/`solar_panel`/`solar_panel_2x1` but no **motor** or **battery**; and the
solar surfaces wanted the WI 624 delight pass to kill baked glare.

## What was generated

- **`motor.glb`** (792 v) — electric drive motor: a finned can on the +X axle with an output shaft
  toward the wheel and a terminal box on top. Origin = body centre (axle-line mount). Skinned with a
  new **`motor_casing`** surface (dark anodized aluminium, concentric machined grooves).
- **`battery.glb`** (304 v) — upright pack box with a lid lip + two top terminals. Origin = base
  centre. Skinned with a new **`battery`** surface (charcoal ribbed-cell casing).
- **Refreshed `solar_cells` + `solar_cells_2x1`** surfaces through the delight pass — even matte
  tone, no central glare; re-skinned `solar_panel` + `solar_panel_2x1`.

## Pipeline notes

- Same flow as the catalog: surfaces via `gen_part_materials.py` (Z-Image albedo on `ai2` + local
  `derive_pbr`), now passing `flatten`/`normal_strength`; geometry via `blender_parts.py` (new
  `motor()`/`battery()` builders, `--only`); skinned via `blender_texture_parts.py` (`SKIN` entries
  added); preview via `render_parts_preview.py` (EEVEE, surfaceless EGL on `ai2`).
- The **delight pass** (`pbr-materials/derive_pbr.flatten_luminance`) is now used by the part-surface
  generator too — flat metal/glossy surfaces (motor casing, solar) read evenly instead of lit.
- glb position bounds verified compact (battery ≈0.22×0.12×0.21 m) — the awkward preview thumbnail of
  the tall battery is the dark-on-dark 3⁄4 EEVEE framing, not a geometry defect.

## Output

`parts/motor.glb`, `parts/battery.glb` + manifest entries; refreshed `parts/solar_panel.glb`,
`parts/solar_panel_2x1.glb`. Catalog now 22 parts. Downstream: Sounding WI 653 Phase B ships these
into `assets/models/parts/` and renders them (gallery scene + workshop/rover).
