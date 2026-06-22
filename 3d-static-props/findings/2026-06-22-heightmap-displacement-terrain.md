# Findings: heightmap-displacement terrain (the clean terrain path)

**Date:** 2026-06-22
**Track:** 3d-static-props
**Verdict:** works — clean, controllable terrain mesh; the right tool for terrain (vs MoGe).

## Goal

After MoGe gave a degenerate stretched sliver on a deep landscape (see
[the MoGe/TripoSR findings](2026-06-22-triposr-moge-test.md)), build the **heightmap-displacement**
terrain path: a regular grid displaced by a heightmap, textured with an albedo — clean topology, no
monocular-reconstruction stretch.

## Tooling (all clean: Z-Image Apache + Blender)

1. `gen_albedo.py` — top-down terrain albedo (Z-Image).
2. `make_heightmap.py` — derive a **smooth macro** heightmap from the albedo
   (autocontrast → downsample → upsample → blur; keeps only large-scale relief so detail stays in
   the texture, not as geometry spikes). **The heightmap source is pluggable.**
3. `blender_displace.py` — grid (`primitive_grid_add`) + `DISPLACE` modifier (heightmap, UV coords)
   → apply → albedo material → export glb. Run on `ai2`'s Blender over SSH.
4. `blender_render_preview.py` — turntable PNGs to eyeball it.

## Result

A textured terrain chunk: **40k tris, regular grid topology, ~4 MB glb**
(`samples-2026-06-22/terrain_displaced{,_oblique}.glb/png`, with `terrain_topdown_albedo.png` +
`terrain_heightmap.png`). Top-down it matches the satellite albedo exactly; oblique shows believable
eroded relief. **No stretch/skirt** — the decisive contrast with the MoGe terrain mesh.

### Iteration (the lesson)

Luminance→height of a *detailed* badlands photo first gave a **bed of spikes** (every shadow a pit,
every fleck a peak). Fix: smooth the heightmap **hard** (downsample to 64px + blur 12) and use **low
strength** (~0.9 over a 10-unit plane) → gentle macro relief, fine detail carried by the texture.
Knobs: `--macro`/`--blur` (relief scale/smoothness), `strength`/`size`/`subdiv` (displace tuning).

## Assessment

- **The clean terrain path works** and is far more controllable than monocular reconstruction —
  regular topology, tunable relief, fully Apache/MIT(+Blender). Use **this for terrain**; keep MoGe
  for near/shallow props (the crate).
- **Quality lever = the heightmap source.** Luminance-derived is "lumpy but clean"; for smoother or
  more accurate relief, plug in a **dedicated Z-Image grayscale heightmap** or a **MoGe top-down
  depth** map into the same `blender_displace.py` step (it doesn't care where the heightmap came from).

## Next

- Swap this good terrain glb into the Sounding `-- terrainmesh` import (the branch currently holds
  the bad MoGe mesh; the scene's CENTER/SCALE need retuning — this terrain is a flat ~10u plane).
- Try a dedicated heightmap source for smoother hills; add tiling for large terrains.
- Texture downscale/KTX2 for game weight (shared with the other 3D cleanup).
