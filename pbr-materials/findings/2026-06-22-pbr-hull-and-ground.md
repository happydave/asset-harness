# Findings: first PBR material sets for Sounding (hull panel + rocky ground)

**Date:** 2026-06-22
**Track:** pbr-materials
**Verdict:** works (pipeline proven; in-engine verification in Sounding pending)

## Goal

Produce tileable, Bevy-ready PBR material sets from the clean Z-Image stack, and confirm the
channel layout Sounding's `StandardMaterial` needs.

## Tooling

- **Albedo (on `ai2`):** Z-Image Turbo txt2img (`gen_albedo.py`), prompted flat/shadowless so no
  directional lighting is baked into base color. Apache 2.0.
- **Map derivation (local, `derive_pbr.py`, PIL only — fully clean, deterministic):**
  - **Seamless:** border cross-fade — blend the right margin into the left edge and bottom into
    top (interior untouched; the blend lands on the tile boundary). Replaced an earlier
    half-offset heal that left a visible centre cross.
  - **Normal:** Sobel-style from an autocontrast height proxy, via 1px wrapped shifts (stays
    tileable); +Y-up (OpenGL) by default, `--flip-g` for DirectX.
  - **Roughness:** leveled albedo luminance around a per-material base.
  - **Metallic:** flat per material.
  - **AO/occlusion:** cavity from height vs blurred height.
  - **Packed `metallic_roughness`:** R=0, **G=roughness, B=metallic** (Bevy/glTF convention).
- **Driver:** `generate_materials.py` (albedo → derive, per material) + a tiled preview.

## Licensing

Z-Image (Apache 2.0) for albedo; all derivation is our own PIL code. **No DeepBump (GPL), no
extra models/nodes installed.** Effective license: Apache 2.0 — clean-pack safe.

## Hardware

Albedo on `ai2` (AMD R9700, gfx1201); derivation runs locally (CPU/PIL). No GPU needed for maps.

## Result

- **Two material sets** (`samples-2026-06-22/`): `hull_panel` (metal 0.85) and `rocky_ground`
  (metal 0.0), each with albedo / normal / metallic_roughness / occlusion / height + tiled preview.
- **Tiling:** clean after the border cross-fade — the 3×3 previews show no seam lines and no heal
  artifact. Ground tiles especially well; hull keeps its panel grid.
- **Maps verified visually:** normals show panel-seam relief; metallic_roughness packs correctly
  (cyan = B-metallic high, roughness detail in G).

## Bevy `StandardMaterial` usage

```rust
fn load_pbr(asset_server: &AssetServer) -> StandardMaterial {
    // Non-color maps MUST load as linear (is_srgb = false). Base color stays sRGB (default).
    let linear = |path: &'static str| {
        asset_server.load_with_settings(path, |s: &mut ImageLoaderSettings| s.is_srgb = false)
    };
    StandardMaterial {
        base_color_texture: Some(asset_server.load("materials/hull_panel_albedo.png")),
        normal_map_texture: Some(linear("materials/hull_panel_normal.png")),
        metallic_roughness_texture: Some(linear("materials/hull_panel_metallic_roughness.png")),
        occlusion_texture: Some(linear("materials/hull_panel_occlusion.png")),
        perceptual_roughness: 1.0, // multiplier; texture supplies the variation
        metallic: 1.0,
        ..default()
    }
}
```

Caveats to confirm in-engine:
- **Tangents:** normal mapping needs mesh tangents — generate them (`Mesh::generate_tangents` /
  `with_generated_tangents`) if the mesh lacks them.
- **Green channel:** if lighting looks inverted, re-derive with `--flip-g` (OpenGL vs DirectX).
- **Color space:** load normal/MR/occlusion as linear (shown above); base color sRGB.

## Repeatability

Deterministic (fixed seed); `materials_manifest.json` records seed/prompts/maps; `derive_pbr.py`
is pure and re-runnable from a saved albedo without regenerating.

## Known limitations

- Single-image derivation is an **approximation** — normals/AO infer relief from albedo, so
  low-relief surfaces yield subtle normals. Fine for mid/background; hero surfaces may later want
  a real height/delight model.
- One 1024 tile repeated shows **repetition** at distance — mitigate with larger tiles, variants,
  or detail/macro blending in-shader.

## Next

- Import a set into **Sounding** and verify lighting/tangents/green-channel (Sounding-side work item).
- More materials (painted panel, ice, sand, carbon, glass); a small material library + manifest.
- Optional: a height/delight model for hero surfaces if quality demands it.
