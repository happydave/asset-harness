# Findings: Blender cleanup step + MoGe put to real use (terrain)

**Date:** 2026-06-22
**Track:** 3d-static-props
**Verdict:** works — clean (MIT) image→3D→game-LOD path proven end-to-end for **terrain/relief**.

## Goal

(1) Add a mesh-cleanup (decimation) step so raw image-to-3D output is game-ready; (2) put the
working MoGe path to real use on terrain (the Sounding ground/LOD/backdrop need).

## Infra note (how Blender runs)

`ai2` (192.168.2.126) is a **separate box** from the workstation (192.168.2.133); Blender 4.0.2
is on `ai2`, my shell is on the workstation. So Blender is driven **over SSH** (`ssh ai2 'blender
--background --python …'`), scp'ing the glb across. Reusable script: `prototypes/blender_decimate.py`
(`import glTF → COLLAPSE-decimate → export glTF`, textures/UVs preserved).

## Results

### Blender cleanup — works

| Mesh | In faces | Out faces | Ratio | Size in→out | Textured |
|---|---|---|---|---|---|
| MoGe crate | 1,123,370 | 22,466 | 0.02 | 25 MB → 3.4 MB | ✅ kept |
| MoGe terrain | 2,037,874 | 101,893 | 0.05 | 47 MB → 13 MB | ✅ kept |

Collapse decimation preserves UVs/texture; one CLI knob (`ratio`) sets the LOD. Sample:
`samples-2026-06-22/crate_cleaned_22k.glb`.

### MoGe on terrain — the real-use payoff

A Z-Image canyon concept (`terrain_canyon_input.png`, Apache) → MoGe →
**`moge_terrain_00001_.glb`** (textured relief; 2.04M tris raw) → decimated to **~102k tris**.
The normal render (`moge_terrain_normal.png`) shows correct relief — canyons cut in, mesas/ridges
raised. This is a genuinely usable **terrain heightmesh from a single image**, exactly the
ground/LOD/backdrop use MoGe fits.

## Assessment

- **A clean, local, AMD-working 3D path now exists end-to-end:** Z-Image concept (Apache) → MoGe
  relief (MIT, gfx1201) → Blender decimate (GPL tool, but its *output* isn't encumbered) → glb.
  Best for **terrain / relief / backdrops**.
- **Caveats:** MoGe is **single-view 2.5D** (no back face — terrain/relief, not closed props);
  cleaned terrain glb is still **13 MB** because the **1024 texture is embedded** — downscale/atlas
  the texture for game use (a follow-up). Ground-plane separation (for discrete props like the
  crate) is still manual.

## Next

- Texture downscale/compression in the cleanup step (KTX2/lower-res) — the glb size is now texture-
  bound, not geometry-bound.
- Import a MoGe terrain chunk into **Sounding** and view (Sounding-side work item; Bevy loads glb
  natively — note MoGe's +Y-up / scale).
- Full-object clean props still blocked: TripoSR Flowty node is single nightly build with a
  `state_dict` key mismatch (would need a custom/forked node); TRELLIS on the NVIDIA box remains
  the hero-quality clean route.
