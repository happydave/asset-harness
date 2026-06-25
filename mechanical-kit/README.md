# Track: mechanical-kit

**Status:** 🟡 rover part catalog in [`parts/`](parts/) (7 **AI-textured** glb + manifest,
mount-at-origin, metres, Y-up) for Sounding WI 608 — parametric Blender shape + AI PBR surfaces
(pbr-materials). See [discover.md](discover.md), [catalog](findings/2026-06-24-rover-part-catalog.md)
+ [surfaces](findings/2026-06-24-part-surfaces.md) findings. Next: rocket-domain catalog
(tank/bell/nose/fins/decoupler).

## Purpose

Modular mechanical part meshes. **Primary consumer: Sounding's `Part` catalog (WI 608)** — the
voxel-skinning design explicitly defers authored per-part meshes to this track. Catalog now spans
**rover** (tire/rim/suspension/seat/antenna/solar/bumper + variants), **rocket-domain**
(tank/nose/engine-bell/decoupler/fin), and **fittings** (round+rect hatch, small+large dish, tablet)
— 20 parts in [`parts/`](parts/). These are mostly revolved solids with consistent mount points,
which whole-mesh AI generation is *worst* at. (DWA is 2D — its modules are served by the `2d` track.)

## Approach (validated)

- Build parts **parametrically in Blender** (bpy primitives + modifiers; geometry nodes optional) —
  primitive shapes, achievable without modeling skill; confirmed runnable headless on `ai2`.
- Let AI supply the **surface**: PBR materials (from [pbr-materials](../pbr-materials/)) + decals.
- Export glTF with **origin at the mount point, metres, Y-up, cell_size-parameterised** (matching
  Sounding's `Part.mount`).

## Licensing

Fully clean: Blender (GPL — outputs are yours) + our geometry + Z-Image surfaces (Apache). The clean
3D lane, with none of the Hunyuan community-license baggage the `3d-static-props` hero path hit.

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
