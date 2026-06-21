# Track: vfx

**Status:** ⚪ not started

## Purpose

Visual effects — flames, sparks, bug-splats, etc. (Sounding).

## Approach (to validate)

- Generate the **base particle texture(s)** with AI.
- Do the *motion* with the engine's particle system (Bevy `hanabi`, Phaser particles) rather
  than generating full sprite-sheet animations — usually higher quality and far cheaper.

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
