# Clamor motion session — 2026-07-27, corrected 2026-07-28

Two more Clamor music videos, this time **with real motion** (Wan i2v). Two songs from the two unused
clamor-night lore stories, with motion accents woven into the stills.

> **CORRECTION (2026-07-28).** The first cut used a **single-stage** Wan shortcut and the clips had
> artifacts (anime-ish figures popping in, morphing). Owner pointed at ai2's saved **`wan2.2-test`**
> ComfyUI workflow. Replicating it (proper **two-stage fp16**) fixed the clips completely. The section
> below is the corrected recipe; the single-stage approach is **abandoned**.

## Wan i2v — the working recipe (replicating `wan2.2-test`)

The saved workflow at `ai2:/opt/comfyui/user/default/workflows/wan2.2-test.json` is the **two-stage MoE
done properly**, and it produces clean, coherent motion. Its exact config:

- **Two-stage**, both experts: high-noise runs sampler steps **0→2**, hands the latent to low-noise for
  steps **2→4** (`return_with_leftover_noise` on stage 1, `add_noise=disable` on stage 2).
- **fp16 checkpoints** (`wan2.2_i2v_high/low_noise_14B_fp16`), **not** fp8_scaled — plus both
  `lightx2v_4steps` LoRAs (one per stage).
- 4 steps, **cfg 1**, **euler / simple**, ModelSamplingSD3 **shift 5**.
- **1280×720**, **33 frames** @ 16 fps (~2.06 s).
- **scene-description prompts** with gentle motion verbs ("zombies slowly stumbling"), not camera-move
  language. This matters — camera-heavy prompts drove the single-stage drift.

`generate_clip.py` already builds this exact graph and has a `--fp16` flag; the fix was just to use it
(two-stage) instead of the invented `generate_clip_single.py`. Driver: `clamor2_clips_v2.py`.

### Why single-stage failed and two-stage works
Wan2.2 is a **MoE that needs both experts** — high-noise for structure/motion at high noise, low-noise
for detail at low noise. Running **one** expert over the whole schedule is off-distribution: low-noise
alone wanders (night→day, anime pop-ins, scene morph); high-noise alone softens and barely moves. The
two-stage hands off between them and stays coherent — the horde clip keeps the city, moon, red lights and
figures intact end-to-end while the crowd shuffles and the mist churns.

### Cost & memory (the archie-night thrash, re-examined)
Archie-night called two-stage "impractical (17+ min, VRAM thrash)". That was the **fp8** path. The **fp16
two-stage actually runs**: because the schedule is split 2/2, only **one 28 GB model is resident at a
time** — high loads (mostly resident, ~1.9 GB spills to lowvram), does 2 steps, then **swaps once** to
low for 2 steps. VRAM peaks ~33.5/34 GB — tight but not OOM. Cost is **~6–10 min/clip** (fp16 loads
dominate: each 28 GB model is read from disk per clip). Slow, but correct — fine for a handful of accents.
Restarted ComfyUI first for a clean VRAM slate (heaviest job on the box); the box stayed healthy
throughout.

## What got made

- **[lyrics.md](lyrics.md)** — two new songs from the **unused** clamor-night lore (session 1 used the
  Scout + gate-keeper; these use the Screamer and the Medic):
  - **"Told the City"** — a Screamer wakes the dead city; the run goes loud, holding the door (driving
    post-punk, 140 bpm, E minor). Ends on the rare good outcome — four in, four out, *everybody's here* —
    the bright mirror of session-1's short-count "Count the Faces".
  - **"Grit"** — the Medic spends his last Grit to Stabilise a man at forty feet (slow ballad, 66 bpm,
    C minor).
- **6 song candidates** (turbo, −1 dBTP, none truncated). Best by Audiobox CE: **Told → seed303**
  (CE 7.10), **Grit → seed301** (CE 7.66).
- **16 stills** (Z-Image base, 1280×720) — dead-city cold-blue + red alarm for Told, muted cold-with-one-
  warm-pulse for Grit. Standouts: the horde on the moonlit boulevard; the four survivors reaching the
  warm Hold gate at dawn; the golden Stabilise pulse.
- **4 Wan i2v motion clips** (two-stage fp16, 1280×720, 33 f): `city_turns`, `horde`, `the_run` (Told),
  `stabilise` (Grit) — all clean and coherent.
- **Two videos** (75.0 s, 1280×720 h264+aac, verified), stills + motion mixed by a hand-authored
  variable-duration beat map (motion clips get ~3 s windows so the settle is brief):
  - `video_told/clamor2_told.mp4` — "Told the City" (**3 motion clips**)
  - `video_grit/clamor2_grit.mp4` — "Grit" (**1 motion clip** — the ballad stays composed)

## Pipeline notes

- **The renderer already supported mixed shots** (`kind: "video"` fits a clip to its window: scale/crop
  to 1280×720, hold last frame if short, trim if long) — no engine change; only a build script with
  per-shot durations.
- **Single-stage Wan does not poison the ACE model-manager state** (still true, and useful): this session
  ran Wan then ACE songs, which ran at the proper ~13 s turbo speed. But single-stage's clip *quality* is
  the problem, so it's abandoned for delivery.

## Reusable / follow-ups

- `clamor2_clips_v2.py` — the two-stage fp16 clip driver (the working recipe; replicates `wan2.2-test`).
- `../../generate_clip.py --fp16` — the underlying two-stage generator (already existed; this is the path
  to use). `../../generate_clip_single.py` is kept only as a record of the failed single-stage experiment.
- Session drivers: `clamor2_songs.py`, `clamor2_stills.py`, `build_clamor2_video.py`.
- Speed idea worth a WI: two-stage with **fp8** models under the *same 2/2 split* (14 GB each, both could
  stay resident → one swap, faster loads) — if fp8 quality is acceptable, it would cut the ~6–10 min/clip
  substantially. fp16 was used here for fidelity to the known-good workflow.
- All under `outputs/clamor-motion/` (gitignored). Nothing committed — play session.
