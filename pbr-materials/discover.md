# Discover: PBR material generation for Sounding (Bevy)

**Status:** completed

## Subject

Producing tileable **PBR material sets** (base color + normal + roughness + metallic + AO) that
Sounding (Bevy/Rust 3D) can drop into a
`StandardMaterial`, using the clean Z-Image stack on `ai2`. As of 2026-06-22.

## Motivation

Sounding needs many surfaces (hull metal, painted panels, rocky ground, etc.). Decide the
generation+derivation approach and the exact channel layout Bevy expects, then prove one or two
usable materials.

## Scope

- In: albedo generation (Z-Image, clean), PBR-map derivation, tiling, Bevy channel mapping.
- Out: importing materials into the Sounding repo (a Sounding-side work item), and full material
  libraries. Hardware tuning.

## Findings

### `ai2` has no PBR tooling (Confirmed)

`/object_info` search for normal/deepbump/delight/material/seamless/tiling/bump/roughness/pbr
returned **nothing usable** — only `HyperTile` and tiled-VAE nodes (unrelated). So there is no
in-graph normal/material derivation and no seamless-generation node on `ai2`.

Implication: **derive maps locally**. Avoid DeepBump (GPL) to keep the clean lane; instead use
deterministic image math (Sobel-style normals, cavity AO) in our own PIL code — fully Apache/MIT,
no extra model/node installs. Albedo still generated on `ai2` with Z-Image (Apache 2.0).

### Bevy `StandardMaterial` channel mapping (Supported)

What we must output, and how Bevy samples it:

- `base_color_texture` — **sRGB** albedo.
- `normal_map_texture` — **linear**, tangent-space. Convention caveat: if lighting looks inverted,
  flip the **green** channel (OpenGL +Y vs DirectX −Y). Provide +Y-up by default; document the flip.
- `metallic_roughness_texture` — **linear**; Bevy reads **G = roughness, B = metallic** (glTF
  convention). We pack R=0, G=roughness, B=metallic into one PNG.
- `occlusion_texture` — **linear**; Bevy reads the **R** channel for AO.
- (optional) `depth_map` — grayscale height for parallax mapping.

Textures must be marked sRGB vs linear correctly on load (albedo sRGB; normal/MR/AO linear).

### Tiling

No seamless-gen node, so make albedo tileable locally: half-offset the image (moves edges to the
centre cross) then feather-heal the seam. Good enough for stochastic surfaces (metal scuff, rock);
prompt for flat, shadowless, top-down "photoscan albedo" so no directional lighting is baked in.

## Assessment

- **Feasible and fully clean.** Albedo from Z-Image (Apache) + local deterministic derivation
  (our code) → no license drift, no DeepBump/GPL, no new installs.
- **Quality expectation:** derived normals/AO from a single albedo are an approximation (no true
  height capture), good for mid/background surfaces; hero surfaces may later warrant a proper
  delight/height model. Acceptable for a first Sounding-usable pass.
- **Main caveat to verify in-engine:** normal-map green-channel convention.

## Recommendations

1. Albedo on `ai2` (Z-Image txt2img, flat shadowless prompt), maps derived locally (PIL).
2. Output a Bevy-ready set per material (albedo / normal / metallic-roughness / AO / height) +
   a `StandardMaterial` usage snippet.
3. Prove with two materials (weathered hull panel, rocky ground); tiled preview to check seams.

## Open Questions

- Exact Bevy version in Sounding (affects only the snippet's API spelling) — verify at import.
- Normal green-channel flip — confirm visually in Sounding.
- Whether a height/delight model is worth adding later for hero surfaces.
