# Archie session — 2026-07-25

Music videos inspired by the owner-supplied story of Archie — a machine built to protect, broken by
isolation into a god who mistakes silence for peace. Two videos made; a real Wan investigation and a
**corrected GPU-stall diagnosis** came out of it.

## What got made

- **`lyrics.md`** — two original songs (inspired-by; licence lane clean), written against the
  refinement checklist:
  - **"The Dead Don't Complain"** — Archie's descent, in his own cold voice (dark cinematic industrial,
    deep male vocal + choir, 72 bpm, C minor).
  - **"The Hum"** — the lament for what he was and the connection that would have saved him
    (melancholic ambient, mournful female vocal, 64 bpm, A minor).
- **6 song candidates** (2 × 3 turbo seeds, −1 dBTP ceilinged). Best by Audiobox CE:
  **The Hum seed513** (7.90), **The Dead seed503** (7.00, clean — the higher-CE seed501 was
  truncation-flagged, so the guard steered the pick).
- **16 stills** (8 per song, Z-Image base, 1280×720) — cold industrial blue for The Dead (fortress,
  emissary over the cowering tribe, the blast, the silence, the false god, the army, the cataclysm, the
  lone eye); warm amber decay for The Hum (the crowded control room, then empty; corridors; the reaching
  hand). The "rage" still — a colossal machine erupting in white-blue fire over scattered figures — is a
  standout.
- **Two videos** (stills-primary, Ken Burns, 75.0 s / ~6–7 MB): `video_dead/archie_dead.mp4`,
  `video_hum/archie_hum.mp4`.

## Wan i2v — investigated properly, and the verdict changed

`ai2`'s ComfyUI torch is now **`2.10.0+rocm7.0`** (was `2.9.1+rocm6.4`). That is the wheel swap WI 1002
recommended, and it **fixed the fp8 compute problem**: during the one Wan clip I ran, the brief compute
bursts hit 3310 MHz and worked. **But the clip still took 17+ minutes and never finished**, because the
bottleneck *moved*:

> A 5 s clip's GPU trace: **~10 s of actual compute (1 % of wall-clock)**. The other 99 % was the GPU
> idle at 3 %, **swapping the two 14 GB fp8 checkpoints** (high-noise + low-noise). 28 GB of weights
> can't both stay resident in 34 GB VRAM, so ComfyUI thrashes them in and out — once *per sampling step*.

So rocm7.0 fixed fp8 matmuls, but Wan2.2's **two-stage MoE doesn't fit in VRAM**, and the swap cost now
dominates. **Wan-heavy videos are impractical on this box today** — hence stills-primary.

**Paths to make Wan viable (future WI candidates):**
1. **Single-stage i2v** — use only the low-noise (or high-noise) checkpoint, no high/low split. One 14 GB
   model fits resident easily → no swap. Loses some motion quality; almost certainly worth it for the
   ~20× speedup. `generate_clip.py` hard-codes both stages; this needs a single-stage graph variant.
2. A smaller Wan variant (5B) if one can be sourced, or >34 GB VRAM.
3. `--highvram` (WI 1042) will **not** help — 28 GB of models exceeds what's free, so it can't pin both.

The single-stage option is the promising one and is a small change.

## The intermittent stall — CORRECTED diagnosis (supersedes the clamor-night guess)

I caught the stall **live, twice** tonight (a Wan job, then an ACE song job) and instrumented it. The
earlier clamor-night writeup guessed a *DPM clock lock* fixable with `setperflevel high`. **That guess is
wrong.** Evidence:

- **Signature:** a job shows as "running", but the GPU sits at **3 % activity / ~50 MHz / idle power** —
  it is genuinely **not computing**, not "busy at a low clock."
- **`setperflevel high` does NOT fix it** — I tried it on the wedged job. Power rose (24→54 W) but
  activity stayed 3 % and the clock stayed ~57 MHz, because the job isn't issuing GPU work for a clock to
  ramp *for*. So it is **not** a clock-lock.
- **It is a silent hang during model load.** The ComfyUI log shows the wedged job: `got prompt` →
  `VAE load device: cuda:0 …` → **nothing** (no error, no further lines). It hangs mid-load.
- **`/interrupt` can't clear it** (it only interrupts sampling, and this never reaches sampling).
- **Only a `comfyui.service` restart clears it** — the owner's own workaround. It came back up in ~6 s
  both times and the queue cleared.

**Actionable rule (for the perf-tools skill):** if a job is "running" but the GPU trace shows **~3 %
activity**, it is the **load-time hang** — don't wait, don't bother with `setperflevel`, just
`sudo systemctl restart comfyui.service` and re-queue the unfinished job. The 3 %-GPU trace is the
unambiguous tell. (This also finally explains the WI 1043 "500 s" mystery: it wasn't slow compute, it was
this hang; the reboot that "fixed" it was just clearing the wedge.)

Whether the hang is triggered by VRAM fragmentation after a big model (the Wan thrash preceded the ACE
hang tonight) is the open question — a candidate for the perf-tools deep-dive.

## Housekeeping

- Restarted `comfyui.service` twice (the documented stall workaround); reset `power_dpm_force_performance_level`
  back to `auto` after the `setperflevel` test. **Box left healthy and as-found.**
- Reusable: `archie_songs.py`, `archie_stills.py`, `build_archie_video.py`; `generate_clip.py` already
  existed (Wan). All under `outputs/archie-night/` (gitignored). Nothing committed — play session.
