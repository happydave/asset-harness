# Findings: Sounding biome terrain library (WI 871)

**Date:** 2026-07-07
**Track:** pbr-materials
**Verdict:** works — 10 tileable terrain sets generated, tiling-audited at 1×/3×3/8×8, and
delivered into Sounding `crates/app/assets/materials/` for the biome layer (B5 splatting)

## Goal

The visual-identity half of Sounding's biome chunk: one 4-map PBR set per `texture_set` name in
the biome table — `grass`, `steppe`, `sand`, `mud`, `forest_floor`, `rock`, `snow`,
`regolith_fine`, `regolith_coarse`, `basalt`. Tiling artifacts at planetary viewing distance were
the named risk, so multi-scale tiling audit is first-class here.

## Tooling

- Driver: `prototypes/gen_material_library.py` terrain section — same stack as the structural
  library (Z-Image Turbo txt2img on `ai2`, gfx1201; local PIL derivation via
  `prototypes/derive_pbr.py`). 1024², 8 steps; per-set seeds in `materials_manifest.json`.
- **New: `derive_pbr.tone_balance`** (per-material `tone` key) — anchors the albedo's mean sRGB
  to the consuming biomes' tint mean: per-channel multiplicative gain **capped at 2×** with the
  remainder as an additive offset. Guarantees the biome layer's far-LOD tint → near-texture hue
  agreement by construction instead of prompt luck; the cap keeps a near-empty channel from
  blowing bright details out to a false colour (see failure modes).
- **New: `prototypes/audit_tiling.py`** — per-set 1× / 3×3 / 8×8 audit strips + a labelled
  contact sheet; `--check-dir` verifies the delivered 4-map contract (presence, exact naming,
  1024², decodable). The 8×8 panel is what catches a "grid beat" invisible at 1×.

## Output

`prototypes/outputs/library/<name>/` (gitignored) + merged `materials_manifest.json`; delivered
contract maps (`<name>_{albedo,normal,metallic_roughness,occlusion}.png`) in the Sounding repo.
Committed evidence: [samples-2026-07-07/](samples-2026-07-07/) (downsampled contact sheet +
one full-res-quality albedo sample).

| Set | tone anchor (sRGB) | rough_base | Notes |
| --- | ------------------ | ---------- | ----- |
| `grass` | 0.35, 0.48, 0.22 | 200 | muted olive turf; seed 777001 + flatten |
| `steppe` | 0.50, 0.47, 0.30 | 210 | dry tufts on cracked soil; distinct-feature repetition visible but even |
| `sand` | 0.74, 0.65, 0.44 | 215 | fine close ripples; seed 777002 + flatten |
| `mud` | 0.20, 0.28, 0.16 | 140 | matte damp swamp mud (smoothest of the batch) |
| `forest_floor` | **0.20, 0.28, 0.10** | 195 | moss + needles; tone is a deliberate compromise (below) |
| `rock` | 0.40, 0.39, 0.38 | 190 | fractured scree; serves 4 biomes, kept hue-neutral |
| `snow` | 0.85, 0.90, 0.95 | 140 | packed snow/firn; gentle normals (2.5) |
| `regolith_fine` | 0.51, 0.50, 0.49 | 225 | grey powder, no rocks; seed 777005 + flatten |
| `regolith_coarse` | 0.35, 0.35, 0.36 | 210 | even scattered fragments; seed 777006 + flatten |
| `basalt` | 0.22, 0.22, 0.23 | 190 | near-black vesicular lava plain |

All ten albedo means land within 0.009 of their anchors (forest_floor of its compromise anchor).

## Failure modes found (and the levers that fixed them)

Four generation rounds total; the audit sheet drove every re-roll:

1. **First-roll composition failures (7 of 10)**: stripe beats (grass "mowing lines"), large
   features knotting at seams (sand dunes), baked sheen gradients (wet mud), clustered features
   beating at 8×8 (forest moss, boulders), repeated dark specks reading as a dot grid at
   distance (snow debris, regolith rocks). Fixed with the structural-library levers: *uniform
   density edge to edge* wording, explicit negatives (`no stripes`, `no footprints`,
   `no rocks`), `flatten`, fresh seeds.
2. **Colour bias resists prompting**: "muted olive"/"pale desaturated beige" still came back
   saturated lawn-green/orange. Prompt-space correction plateaued after two rounds —
   `tone_balance` (deterministic post) is the reliable lever, same philosophy as the WI 624
   delight lesson: *fix in post what the model insists on baking in*.
3. **New: the framed-swatch failure** — one forest_floor roll rendered the texture as a bordered
   swatch (blue frame edge-to-edge), which tiles into a picture-frame grid. The FLAT formula's
   "texture swatch" wording can elicit this; `full bleed, no border, no frame` added to the
   subject fixed it.
4. **New: tone-matching across hue families distorts details** — matching a green-dominant
   anchor from the model's brown-leaning forest floor halves R and doubles B, turning bright
   needle strands cyan. Root cause: a mean-matching gain acts on *everything*, and bright
   details in a near-empty channel amplify worst. Fix: gain cap + offset in `tone_balance`,
   plus accepting a compromise anchor for that one set (the far-tint drift is small; the B5
   splat can tint-modulate).

## License chain

Z-Image Turbo (Apache-2.0) albedo + local deterministic PIL derivation (this repo, Apache/MIT).
No LoRA/ControlNet, no hosted services. Effective license: clean for redistribution.

## Downstream

- **Sounding WI 871**: the 40 contract maps + `ATTRIBUTION.md` rows delivered on the `biomes`
  branch (v0.1.189). Nothing loads them until **WI 872 (B5 splatting)**; biomes render by tint
  fallback until then. B5's in-engine UV scale is the remaining unaudited regime (deferred by
  the work item).
- Height maps and tiled previews stay banked here (contract is 4 maps, WI 624 precedent).
