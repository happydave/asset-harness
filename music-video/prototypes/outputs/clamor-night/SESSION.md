# Clamor night session — 2026-07-25

A play session on the harness updates: lore-grounded lyrics, two music videos, and a live hunt for the
ACE-audio GPU stall. `ai2` was free for the night.

## What got made

- **`lore.md`** — a working world-bible for **the Hold** (the colony) + four mini-stories tied to
  specific game mechanics (a Scout's Silent Move, a Medic's last Grit, a Screamer breaking the silence,
  the gate-keeper's arithmetic). Grounded in the game's own vocabulary from `design-gameplay.md`.
- **`lyrics.md`** — a reusable **lyric-refinement checklist** for ACE-Step + two new songs written with
  it, one shown as draft→critique→revise so the method is legible:
  - **"The Quiet Mile"** — the Scout's creed (hushed indie folk, 96 bpm, A minor).
  - **"Count the Faces"** — the gate-keeper's ledger (slow folk ballad, 72 bpm, D minor).
- **6 song candidates** (2 songs × 3 turbo seeds), all `-1 dBTP` ceilinged. Best by Audiobox CE:
  **quiet_mile seed903** (7.88), **count_the_faces seed911** (7.79). The truncation guard **fired live**
  on count_faces seed912 — and that seed also scored lowest CE, independent corroboration.
- **16 stills** (8 per song, Z-Image base, 1280×720) — the city's cold blue for the Quiet Mile, the
  Hold's warm lantern light for Count the Faces. The lyric-grounding paid off visually: "coats on hooks
  that don't turn right" rendered as blank-faced figures standing literally among hanging coats.
- **Two finished videos** (manifest → pure renderer, Ken Burns, `-1 dBTP` audio), 75.0 s / ~7 MB each:
  - `video_quiet_mile/clamor_quiet_mile.mp4`
  - `video_count_faces/clamor_count_the_faces.mp4`

## The turbo pipeline, validated in the wild

Every song generated at **turbo, 12.7–15.2 s**, auto-ceilinged (several came in hot at 0 to +0.1 dBTP
and were trimmed to −1.00). The save-time ceiling and the truncation warning both did their jobs on
songs I didn't hand-pick. This is the first use of the new default outside the WI 1043 test set.

## GPU stall hunt — characterized, not reproduced

The stall did **not** occur tonight (box healthy, uptime ~2.5 h+), but I traced all 22 GPU jobs with
`amd-smi` (logger left at `ai2:~/gpu_trace.py`) and captured a clean **healthy fingerprint**:

| state | gfx % | gfx clock | power |
|---|---|---|---|
| **idle** (between jobs) | 3 % | ~42 MHz | 23 W |
| **healthy compute** (every job) | ~100 % | **1885–3464 MHz** | 304–344 W |

Every one of the 22 jobs ramped hard the instant compute started. So "**foundry reports 3 % GPU**" is
the **idle** signature — if it's showing 3 % *while a job is grinding*, the ramp has failed.

> **CORRECTED 2026-07-25 (archie session) — the hypothesis below was WRONG.** I caught the stall live
> and tested `setperflevel high` on the wedged job: power rose but the clock and 3 % activity did **not**
> — it is **not** a DPM clock lock. It's a **silent hang during model load** (ComfyUI log: `got prompt`
> → `VAE load device…` → nothing). The only fix is a `comfyui.service` restart (the owner's workaround);
> `setperflevel` does nothing. Detection rule stands (3 % GPU during a "running" job = the stall), but
> the fix is **restart, not setperflevel**. See `archie-night/SESSION.md` for the full corrected writeup.

### The actionable hypothesis for next time (SUPERSEDED — see correction above)

The WI 1043 note recorded the stall state as "99–100 % GPU, just ~20× slower." Combined with tonight's
data, the most likely mechanism is **a DPM clock lock**: the GPU stays *busy* but its clock is stuck in a
low power state (~500 MHz instead of ~3000), so the same work takes ~20× longer. The "3 % busy" the user
sees is probably a between-jobs sample during that slow grind.

**If it happens again, before restarting ComfyUI, try to fix it live** (a restart may be avoidable):
1. Run the trace during the slow job: `ssh ai2 'python3 ~/gpu_trace.py /tmp/stall.csv 1'` — watch the
   `gfx_clk_mhz` column.
2. **If gfx% is high but the clock is stuck low** (~500–1000 MHz, not 3000+), it's the clock lock. Try
   forcing the high-performance level: `ssh ai2 'sudo rocm-smi --setperflevel high'` (or `amd-smi set`).
   If the job speeds up, the stall is a power-management state, **fixable without a restart or re-queue**.
3. If the clock *does* ramp to 3000+ and it's still slow, that's a different problem (fall back to the
   restart). Either way the trace tells you which.

This is worth folding into the **perf-tools skill** the owner is building — the trace logger + the
"clock stuck low = setperflevel, not restart" rule is exactly that skill's first useful recipe.

## Reusable bits left behind

- `ai2:~/gpu_trace.py` — amd-smi sampler → CSV (gfx%, clock, throttle, PCIe, power, UMC).
- `clamor_songs.py` — the two songs as a turbo driver (ceiling + truncation per job).
- `quiet_mile_stills.py` / `count_faces_stills.py` — themed still batches.
- `build_*_video.py` — direct-manifest video assembly (no ASR timeline needed; even 8-way partition).

All under `outputs/clamor-night/` (gitignored). Nothing here is canon or committed — it's a night of
play. Keep what you like; the lore/lyrics are the parts most worth promoting if any are.
