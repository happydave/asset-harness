# Findings: Sounding structural-material library (+ bonus surfaces)

**Date:** 2026-06-25
**Track:** pbr-materials
**Verdict:** works — 7 Bevy-ready sets generated and (4 of them) imported into Sounding (WI 624)

## Goal

Give Sounding's four **structural** voxel materials (aluminium, steel, titanium, composite) their
own bespoke PBR sets instead of sharing the `hull_panel` texture, and grow the library with a few
planetary-surface materials while the pipeline was warm.

## Tooling

- Driver: `prototypes/gen_material_library.py` — a material list over the existing
  `gen_albedo.generate_albedo` (Z-Image Turbo txt2img on `ai2`) + `derive_pbr.derive` (local PIL
  derivation). Same proven stack as the 2026-06-22 hull/ground run; only the prompt list + per-set
  `metal`/`rough_base` differ.
- Seed 424242, 1024², 8 steps. Albedo on `ai2` (R9700 / gfx1201); derivation local CPU.

## Output

`prototypes/outputs/library/<name>/` + `materials_manifest.json`, each set = albedo / normal /
metallic_roughness / occlusion / height + tiled preview.

| Set | metal | rough_base | Notes |
| --- | ----- | ---------- | ----- |
| `aluminium_panel` | 0.95 | 130 | brushed satin, rivets — reads light silvery |
| `steel_plate` | 1.0 | 95 | polished blue-grey, swirl; faint horizontal repetition |
| `titanium_panel` | 0.9 | 150 | warm grey-gold satin, milling marks |
| `carbon_weave` | 0.1 | 120 | charcoal 2×2 twill — the strongest of the four |
| `sand_dune` | 0.0 | 215 | wind-rippled tan sand |
| `ice_sheet` | 0.0 | 75 | cracked pale blue glacial ice |
| `basalt_rock` | 0.0 | 185 | dark vesicular volcanic rock |

## Result

- All seven tile cleanly (border cross-fade) and the four structural sets read **distinctly by
  colour alone**, so the engine can relax its per-material tint and let the real albedo lead.
- Single-image derivation limits (subtle normals on low-relief surfaces) apply as before — fine for
  mid/background; carbon weave's strong pattern gives it the best relief.

## Metals need a delight pass (in-engine feedback)

The first metal rolls read as **lit**, not flat: Z-Image Turbo at cfg 1.0 (no negative guidance)
bakes a large highlight sweep into a "flat metal" prompt — titanium a **radial spin** that *quartered*
when tiled, steel a vertical band — with little fine detail. Stripping detail words made it worse
(featureless gradients). Two fixes, now part of the pipeline:

- **`derive_pbr.flatten_luminance` (new, `--flatten`)** — pure-PIL delight: subtract the
  low-frequency luminance (big Gaussian) and re-centre each channel to its mean, cancelling the
  baked gradient/vignette while preserving high-frequency grain. The reliable, model-agnostic lever.
- **Prompt direction reversed** — push *dense edge-to-edge micro-detail* (so the model fills the
  frame with texture instead of one lit sweep) and drop "brushed/satin/polished" sweep words; a
  fresh seed breaks a stubborn radial composition (titanium).
- **Per-material `normal_strength`** — gentler on smooth metals (2.5–3.5), full on the carbon weave
  (4.0) to keep the twill relief.

Driver gained subset regen (`gen_material_library.py <name>...`), a merged manifest, and per-material
`seed` / `normal_strength` / `flatten` keys. Carbon also re-rolled with `flatten` for an even tone.
Lesson: for flat metal albedo, **delight in post** beats fighting the txt2img model's lighting.

## Downstream

- **Sounding WI 624:** imported the 4 structural sets into `crates/app/assets/materials/`; pointed
  `voxel_skin::material_set_for` at them; relaxed the skin tint (albedo-led) and made metal/roughness
  texture-driven. The 3 surface sets are banked here, not yet imported (no Sounding consumer).

## Next

- A Sounding consumer for the planetary surfaces (per-planet ground material) would pull `sand_dune`
  / `ice_sheet` / `basalt_rock` the same way `rocky_ground` is used today.
- Rocket-domain materials when that catalog lands (heat-shield, painted panel).
