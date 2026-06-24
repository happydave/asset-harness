# Findings: thruster SFX set — start / burn / stop

**Date:** 2026-06-24
**Track:** audio (sfx sub-stream)
**Verdict:** works

## Goal

Complete the hauler engine into a proper lifecycle: **ignition** (`thruster_start`), **sustained
burn** (existing `thruster_loop`), and **shutdown** (`thruster_stop`) — for DWA. Builds on
[the SFX prototype](2026-06-23-sfx-stable-audio-3.md).

## Tooling

Same clean stack: Stable Audio 3 Medium Base on `ai2` via
[`generate_sfx.py`](../prototypes/sfx/generate_sfx.py) (entries `thruster_start` seed 105,
`thruster_stop` seed 106); ffmpeg post via
[`optimize_audio.py`](../prototypes/optimize_audio.py). Licensing/provenance unchanged from the
prototype findings (Stability Community License, fully-licensed data, <$1M ceiling + Gemma terms).

## Approach

- **Cohesion:** start/stop prompts reuse the loop's engine language ("steady low-frequency rumble +
  high-pressure plasma hiss") so the three read as one engine. (Stable Audio gives no hard timbre
  lock across seeds — best-effort via shared language; acceptable here.)
- **Transitions, no in-engine crossfade:** start/stop are one-shot transients layered *over* the
  continuous loop bed on the rising/falling edge of thrust. So the loop carries the body and the
  transients only add ignition/shutdown character.
- **`thruster_start` ends hot:** post with `--fade 0` (new option) so it does not dip before the loop
  is audible. `thruster_stop` keeps a short fade on its natural decay.

## Result

- **Samples:** [`samples-2026-06-24/`](samples-2026-06-24/) (`thruster_start`, `thruster_stop`).
- **Measured (last 80 ms RMS):** start −28.8 dB (ends hot → blends into loop), stop −72 dB (decays to
  silence → clean shutdown). Durations: start 2.04 s (no trailing trim), stop 1.85 s.
- DWA: `make build` passes; all three oggs bundle. `Ship` plays start+loop on the thrust rising edge
  and loop-stop+stop on the falling edge; each is asset-absent safe.

## Next

- If start/stop timbre drift from the loop bothers in play, regenerate the loop from the same seed
  family, or derive start/stop *from* the loop (head ramp / tail decay) in ffmpeg instead of fresh
  generations.
