# Findings: thruster SFX re-roll — de-hiss

**Date:** 2026-06-24
**Track:** audio (sfx sub-stream)
**Verdict:** works

## Goal

Re-roll the full hauler thruster set (loop / start / stop) — the original takes read as
**static**, worst on the shutdown. Builds on [the thruster set](2026-06-24-thruster-set.md).

## Root cause (measured)

The original prompts all carried broadband-noise language — "high-pressure plasma hiss" /
"descending hiss". Spectral check on the shipped oggs (ffmpeg `astats` zero-cross rate;
`aspectralstats` flatness):

| sound | zero-cross (old) | flatness (old) |
|-------|------------------|----------------|
| loop | 0.009 | 0.117 |
| start | 0.005 | 0.046 |
| **stop** | **0.278** | **0.258** |

The shutdown was ~30× the noise content of the others — the "static".

## Approach

- **De-hiss the prompts:** drop "plasma hiss / high-pressure / descending hiss"; describe a
  deep tonal rocket engine (resonant low roar, warm sub-bass rumble, low thump, spool-down),
  explicit "no hiss / no static".
- **Negative prompt** (the generator's was empty): "harsh hiss, white noise, static,
  crackle, distortion, fizz" — actively steers away from the noise. (`generate_sfx.py` now
  threads a per-entry `neg` into the previously-empty negative CLIP encode, plus a `--seed`
  override for cheap re-rolls.)
- Fresh seeds (loop 412, start 415, stop 416). Post unchanged per role.

## Result

| sound | zero-cross (new) | flatness (new) |
|-------|------------------|----------------|
| loop | 0.007 | 0.041 |
| start | 0.025 | 0.081 |
| stop | **0.012** | **0.041** |

Shutdown noise down ~23×; loop cleaner/more tonal. Start is a touch more textured (a
pressurized whoosh — broadband by nature) but far below static. **User-auditioned: "much
better."** Imported to DWA `public/assets/sfx_thruster*.ogg`.

## Lesson

For engine/ambient beds, **the negative prompt is the lever against hiss/static** — Stable
Audio leans noisy when the positive prompt mentions "hiss/plasma/pressure". Keep the body
tonal and reject broadband noise explicitly.

## DWA-side note

The re-rolled set surfaced a *trigger* bug (not an asset issue): the engine audio was gated
on the per-frame thrust flag, which flickers during the orbital lead-intercept → rapid-fire
ignition/shutdown. Fixed game-side by gating the audio (and the fly-by size) on the stable
transit state. Recorded in the DWA WI 630.
