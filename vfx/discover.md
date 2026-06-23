# Discover: VFX — thruster flames (and the VFX approach generally)

**Status:** completed (approach decided; first flame set is the prototype)

## Subject

Generating VFX assets for the games, focused on **thruster flames** (Sounding rockets; DWA ship
exhaust). As of 2026-06-22.

## The core principle

**VFX is motion, and motion is the engine's job** — particle systems and shaders, not pre-baked
assets. So the harness does **not** "generate a flame"; it generates the **textures** a particle
system consumes, and optionally **pre-baked flipbooks** for set-piece effects. This keeps effects
real-time, controllable (throttle, gimbal, flicker), and cheap.

## Thruster flames specifically

A thruster flame = a **particle system + a stretched billboard plume**, driven live:
- **Particle system** at the nozzle: additive flame sprites in a cone along −thrust axis; lifetime
  ~0.1–0.3 s; size/velocity/colour over life; **spawn-rate / plume-length / intensity ∝ throttle**;
  emitter rotates with the gimbal. (Sounding: **`bevy_hanabi`** GPU particles; DWA: **Phaser
  particles** — already has a soft-dot exhaust texture in `Ship.ts`.)
- **Billboard plume** sprite: one vertical flame gradient (white-hot core → orange → blue base →
  wispy tip), stretched along the nozzle and scaled by throttle — cheap and reads great for rockets.

So the **AI-generated assets** are: a **plume** billboard + **particle sprites** (flame puff, spark/
ember, later smoke). The engine supplies all the movement.

## The additive trick (why flames are easy)

Fire/glow is **emissive** → render with **additive blending**, where **black = transparent**. So we
generate flames on a **pure black background** and use the image directly (no matte/cutout needed).
We also emit an **RGBA** variant (alpha = luminance) for alpha-blend pipelines. Smoke is the
exception — it's alpha-blended, so it needs a real matte (a later asset).

## Licensing

All clean: **Z-Image (Apache)** for the sprites; the optional flipbook path uses **Wan2.2 i2v
(Apache, installed on `ai2`)**. No new deps.

## Options & recommendation

1. **Particle/billboard sprites (recommended, this prototype):** Z-Image flame sprites on black →
   additive + RGBA variants → fed to `bevy_hanabi` / Phaser. Real-time, throttle-reactive, both
   engines. The right tool for *thrusters*.
2. **Flipbook via Wan2.2 i2v (secondary):** image→video flame loop → extract frames → sprite-sheet
   atlas. Great for **set-piece / fixed** flames, but a baked loop doesn't react to throttle, so it's
   not ideal for a variable thruster. Worth prototyping later for explosions / one-shot FX.

## Recommendation

Build the **thruster-flame sprite set** (plume + puff + spark) on the clean stack now; document the
`bevy_hanabi`/Phaser wiring; keep the Wan2.2 flipbook for set-piece effects.

## Open questions

- Exact `bevy_hanabi` version/API in Sounding (for a precise snippet) — confirm at import.
- Stylization: realistic vs the games' stylized look (tune palette/prompt per game).
