# Track: mechanical-kit

**Status:** ⚪ not started

## Purpose

Modular, snap-together mechanical parts — Sounding fuel tanks / wings / rocket stages, DWA ship
& station/mothership modules. These are mostly simple revolved solids (cylinders, cones, rings)
that need consistent mount points, which whole-mesh AI generation is *worst* at.

## Approach (to validate)

- Build a small **parametric kit in Blender** (geometry nodes drive variety) — geometry is
  primitive shapes, so this is achievable without modeling skill.
- Let AI supply the **surface**: PBR materials (from [pbr-materials](../pbr-materials/)) and
  decals.
- Export glTF with consistent attachment-point conventions.

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
