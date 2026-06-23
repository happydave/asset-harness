# Findings: thruster-flame VFX sprite set

**Date:** 2026-06-22
**Track:** vfx
**Verdict:** works — clean-stack flame sprites ready for engine particle systems.

## Goal

Generate the **textures** a thruster-flame effect needs (the engine supplies the motion), focused
on Sounding rockets / DWA exhaust.

## Tooling

- `generate_flames.py` — Z-Image (Apache) emissive sprites **on pure black**, three subjects
  (plume / puff / spark), each emitted as `<name>.png` (additive: black = transparent) **and**
  `<name>_rgba.png` (alpha = luminance, for alpha-blend pipelines). Reuses the pbr `gen_albedo`
  Z-Image txt2img. Builds a preview montage.

## Result

`samples-2026-06-22/`: `flames_montage.png` (top = additive on black, bottom = RGBA over checker)
+ `flame_{plume,puff,spark}_rgba.png` + `flame_plume_additive.png`.

- **plume** — vertical exhaust flame (white-hot core → orange, narrowing): the **billboard plume**.
- **puff** — round fireball: particle puffs / explosions.
- **spark** — scattered embers: spark/ember particles.

The additive-on-black trick works: the raw image drops onto an additive emitter as-is, and the
RGBA variant composites cleanly over the checker. All **Apache** (Z-Image) — clean.

## Engine consumption (the motion lives here)

**Sounding (Bevy / `bevy_hanabi`):** an emitter at each nozzle, cone along −thrust axis, **additive
blend**, `flame_puff` as the particle sprite; size/colour/velocity over life; **spawn-rate &
plume-length ∝ throttle**; emitter follows the gimbal. Optionally a single stretched **billboard
plume** quad (the `plume` sprite, additive) scaled by throttle for the core jet, with `puff`/`spark`
particles layered on. (Confirm the installed `bevy_hanabi` version for exact API.)

**DWA (Phaser):** `ParticleEmitter` with `blendMode: 'ADD'` using the flame sprite (replaces the
soft-dot exhaust already in `Ship.ts`); `frequency`/`quantity`/`lifespan` driven by throttle/state.

## Assessment

- The flame **sprite set** is the right deliverable for thrusters: real-time, throttle-reactive,
  works in both engines. The plume reads a bit "burst"-like (more flamethrower than clean nozzle
  jet) — a prompt/seed re-roll or a taller aspect could refine it; fine for a first set.
- Smoke is the notable gap (alpha-blended, needs a real matte, not the black-additive trick) — a
  follow-up asset.

## Next

- Per-game stylization (palette/prompt) + a taller plume aspect; add **smoke** (matte) + **muzzle/
  impact** puffs.
- Optional **Wan2.2 i2v flipbook** for set-piece flames/explosions (baked loop; not for throttle-
  varying thrusters).
- Wire `flame_puff` into a Sounding `bevy_hanabi` thruster (Sounding-side work item).
