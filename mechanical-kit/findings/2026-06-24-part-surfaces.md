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

## Next

- **UV quality:** smart-project is generic; revolved parts (tire/rim) would read better with a
  cylindrical unwrap so the tread/brush aligns with the axle.
- **Decals/greebles** (panel lines, warning marks) as a second texture layer for variety.
- Trim embed size (128 px or shared external textures) if repo weight matters.
- Rocket-domain catalog reuses both scripts.
