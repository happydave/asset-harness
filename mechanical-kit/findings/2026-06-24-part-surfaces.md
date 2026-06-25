# Findings: AI-textured part surfaces (pbr-materials skin)

**Date:** 2026-06-24
**Track:** mechanical-kit
**Verdict:** works

## Goal

The "AI surface" half of the track: skin the [v1 rover parts](2026-06-24-rover-part-catalog.md) with
AI PBR materials instead of flat factor colours, and re-export textured glb for Sounding to retrieve.

## Tooling

- **Materials:** [`prototypes/gen_part_materials.py`](../prototypes/gen_part_materials.py) reuses the
  **pbr-materials** pipeline — Z-Image flat albedo on `ai2` + local derivation
  (`derive_pbr`) to albedo / tangent-normal / packed metallic-roughness (Bevy G=rough/B=metal) / AO.
  Four sets: `metal_panel`, `rubber`, `solar_cells`, `seat_fabric`.
- **Skinning:** [`prototypes/blender_texture_parts.py`](../prototypes/blender_texture_parts.py) — on
  `ai2`, imports each v1 glb, **smart-UV-unwraps**, binds a Principled material (albedo + NormalMap +
  SeparateColor→roughness/metallic) with a per-part **UV tiling scale**, and re-exports. Embedded
  textures downscaled to **256 px** (parts are small) to bound glb size.

## Licensing

Clean: Z-Image (Apache) for the albedo; the rest is deterministic local PIL derivation + Blender
(GPL). No license change from v1.

## Result

- **Outputs:** [`../parts/`](../parts/) glb now carry embedded PBR (manifest updated:
  `material_set` per part, `textured: true`). Preview:
  [`samples-2026-06-24/parts_textured_contact_sheet.png`](samples-2026-06-24/parts_textured_contact_sheet.png);
  materials: [`part_materials_preview.png`](samples-2026-06-24/part_materials_preview.png).
- **Big reads improved:** the **tire** now shows tread, the **solar panel** a real PV cell grid, rim/
  strut/bumper read as brushed metal, the seat as quilted upholstery — a clear lift over flat colours.
- **Size:** glb 0.5–1.2 MB each (~5 MB total) from embedded 256 px textures (seat_fabric/rubber
  compress worst). Acceptable for the integration deliverable; drop the embed size if it bites.
- Bulk material PNGs are git-ignored (regenerable via `gen_part_materials.py`, and embedded in glb).

## Repeatability

- Deterministic (fixed Z-Image seeds; PIL derivation). part→material→UV-scale map lives in
  `blender_texture_parts.py`.

## Update 2026-06-25 — cylindrical unwrap for the wheels

The revolved parts now use a **cylindrical** unwrap about their axle (X) instead of smart-project:
`blender_texture_parts.py:cylindrical_uv` computes per-vertex `u = angle (0..1)`, `v = along-axis`,
with a seam fix for faces crossing the atan2 wrap; tiling is per-axis via the Mapping node (tire
`8×1`, rim `5×1`). Result (see [`samples-2026-06-24/wheel_unwrap_compare.png`](samples-2026-06-24/wheel_unwrap_compare.png)):
the **tire tread now wraps the rolling circumference** and the **rim reads as turned/machined metal**
— a clear lift over the flat smart-project mapping. The flat caps (sidewall/hub) get a radial mapping
(reads as turned metal / radial sidewall — acceptable). Manifest records `uv_unwrap` per part.

## Update 2026-06-25 — variants + steering wheel

Added three parts (preview [`samples-2026-06-24/new_parts_2026-06-25.png`](samples-2026-06-24/new_parts_2026-06-25.png)):
- **`seat_leather`** — seat geometry skinned with a new `leather_light` set (light tan full-grain).
- **`solar_panel_2x1`** — panel geometry with a new `solar_cells_2x1` set (rectangular 2:1 cells).
- **`steering_wheel`** — new geometry (torus rim + 3 spokes + hub) with a **toroidal** unwrap
  (`toroidal_uv`: u = around the wheel, v = around the rim tube) so the leather wraps the rim. The
  scripts gained `--only` so single parts regenerate without touching the rest. Catalog is now 10.

## Next

- **Flat caps:** a separate planar projection for the tire sidewall / rim face would remove the
  residual radial smear (multi-projection per part) — diminishing returns for now.
- **Decals/greebles** (panel lines, warning marks) as a second texture layer for variety.
- Trim embed size (128 px or shared external textures) if repo weight matters.
- Rocket-domain catalog reuses both scripts.
