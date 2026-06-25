# Findings: rocket-domain catalog + fittings

**Date:** 2026-06-25
**Track:** mechanical-kit
**Verdict:** works

## Goal

Extend the part catalog beyond rover parts: the **rocket-domain** set (tank, nose cone, engine bell,
decoupler, fin) plus requested **fittings** (round + rectangular hatch, small + large satellite dish,
handheld tablet). 10 parts; catalog 10 → 20.

## Tooling

Same scripts/stack as the rover catalog: parametric `blender_parts.py` (added a `cone()` helper and
the 10 builders), three new AI material sets via `gen_part_materials.py` (`white_hull`, `heat_metal`,
`screen_ui`), skinned by `blender_texture_parts.py`. All on `ai2`, fully clean (Blender GPL + our
geometry + Z-Image surfaces, Apache).

## Geometry / contract

- **Axial rocket parts** stack along **+Y** (rocket "up"); origin at the bottom mount plane
  (`engine_bell` at the throat). Cylindrical unwrap about Y.
- **Fittings** are wall-mounted: hatches/dish/tablet face **+Z**, origin at the hull-mount centre.
- All keep the catalog contract (origin = mount, metres, glTF Y-up). Manifest records each.

## Result

- **Outputs:** [`../parts/`](../parts/) (20 parts now). Preview:
  [`samples-2026-06-24/rocket_parts_2026-06-25.png`](samples-2026-06-24/rocket_parts_2026-06-25.png).
- **Reads well:** white panel-lined tank/nose, heat-tinted (blue/gold/soot) nozzle, dark decoupler
  band, brushed fin, round hatch with bolt rim, rectangular hatch with frame+handle, both dishes
  (reflector + feed on a stem), and the **tablet shows a glowing cyan UI** on its screen (`screen_ui`
  material via a single screen-per-face UV).
- **Size:** `parts/` is now ~13 MB (20 × embedded 256 px PBR). Flag: drop the embed to 128 px or move
  to shared external textures if repo weight matters.

## Notes / limitations (v1)

- `engine_bell` is a cone frustum (flare is approximate, not a true bell curve); `dish_*` reflectors
  are frustums, not true paraboloids (read as dishes at scale, with the feed); `fin` is a beveled
  plate, not swept. All acceptable at part scale; lathe/spin refinements are future polish.

## Next

- Texture-size optimization pass if repo weight matters.
- Swept fins / true paraboloid dishes / curved bell via a spin (screw) modifier.
- Greebles/decals (panel lines, hazard marks) as a second texture layer.
