# Track: vfx

**Status:** 🟡 thruster flames prototyped — Z-Image emissive sprites on black (additive + RGBA)
for engine particle systems; see [discover.md](discover.md) and the
[thruster-flames findings](findings/2026-06-22-thruster-flames.md). VFX motion stays in the engine
(`bevy_hanabi` / Phaser); the harness makes the textures. All Apache (clean).

## Purpose

Visual effects — flames, sparks, bug-splats, etc. (Sounding).

## Approach (to validate)

- Generate the **base particle texture(s)** with AI.
- Do the *motion* with the engine's particle system (Bevy `hanabi`, Phaser particles) rather
  than generating full sprite-sheet animations — usually higher quality and far cheaper.

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
