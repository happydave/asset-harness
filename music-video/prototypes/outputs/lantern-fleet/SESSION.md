# Lantern Fleet session — 2026-07-26

A self-directed play session: my own universe end to end (lore → refined lyrics → turbo songs → themed
stills → two videos), plus a new, useful GPU finding. Deliberately warm and luminous to break from the
last two sessions' grim industrial palette (Clamor's cold colony, Archie's machine-dread).

## The universe: the Lantern Fleet

An endless amber-violet **dusk** over a silver **cloud sea**; no ground. People live on hundreds of
floating **lantern-islands**, each held aloft by the light of a temple-sized **Beacon** — *light is lift*,
so all of life is the keeping of flame. **Lamplighters** ride winged skiffs across the gulf carrying fire
between islands; their hardest duty is **the mercy cut** — severing a doomed island's bridges before it
falls so it doesn't drag its neighbours down. The dark eats light two ways: the slow **Guttering**, and
the **Moths** — vast sky-creatures that fold over the brightest Beacons and snuff them. Full bible in
[lore.md](lore.md).

Two songs take the two halves of a Lamplighter's life — the same two-POV structure as Clamor's
Quiet-Mile/Count-the-Faces and Archie's Dead/Hum:

## What got made

- **[lore.md](lore.md)** — the world-bible + three mini-stories (the first crossing; the mercy cut at
  Emberfall; the oil-child rite).
- **[lyrics.md](lyrics.md)** — two original songs against the refinement checklist, Song A shown
  draft→critique→revise:
  - **"Lamplighter"** — Wren's first solo crossing; the joy before the cost (warm anthemic folk-rock,
    soaring female vocal, 104 bpm, D major).
  - **"The Island That Went Dark"** — the mercy cut at Emberfall; the name carried for good (melancholic
    folk ballad, weathered female vocal, 68 bpm, A minor). Its bridge reuses the recurring device across
    these sessions — the keeper who reports the saved total and privately withholds the one lost.
- **6 song candidates** (2 × 3 turbo seeds, −1 dBTP ceilinged, none truncated). Best by Audiobox CE (the
  scorer that tracks owner taste):
  - **Lamplighter → seed701** (CE 7.55; the three were within 0.1 CE — a genuine near-tie).
  - **Emberfall → seed703** (CE 8.01, PQ 8.43 — a clear winner over 702/701).
- **16 stills** (8 per song, Z-Image base, 1280×720) — warm gold + paper-red against violet dusk. The
  establishing Fleet (dozens of Beacon-islands over the cloud sea) and the Moth folding over a lone
  Beacon-spire are standouts; the striker shot rendered Wren beaming at her tiller, flame at her collar.
- **Two videos** (stills-primary, Ken Burns, −1 dBTP audio), 75.0 s / ~6–7 MB, verified 1280×720 h264+aac:
  - `video_lamp/lantern_lamp.mp4` — "Lamplighter"
  - `video_ember/lantern_ember.mp4` — "The Island That Went Dark"

## New GPU finding — model eviction after a Wan job, and the restart fix

This session surfaced a **distinct** perf problem from archie-night's load-hang (both belong in the
perf-tools skill; they are different failure modes):

**Symptom.** Every ACE song ran 65–114 s and every Z-Image still ran ~97–173 s — vs archie-night's ~13 s.
The ComfyUI log showed *every single job re-loading its full model set from disk*: each still reloaded
ZImageTEModel (7.6 GB) **and** Lumina2 (11.7 GB) = ~19 GB, each song reloaded ACE15TEModel (9.1 GB) **and**
ACEStep15 (9.5 GB). The GPU still ramped and jobs completed — this is **not** the load-hang (that sits at
3 % forever and needs a restart to clear a *wedge*). It's just slow.

**Root cause.** ComfyUI was **evicting the resident models between every job** and re-reading them from
disk, even though VRAM was only **14.5 GB used of 34 GB** — no memory pressure at all. `--disable-mmap`
(the WI 1054 fix) was confirmed active, so this is not the mmap-page-fault stall either. The trigger was
**today's earlier Wan2.2 job**: it loaded two 14 GB fp8 checkpoints in `lowvram`/partial mode
(`loaded partially … 6551 MB offloaded, lowvram patches: 129`), which left ComfyUI's model manager in a
conservative offload-everything state that persisted for all later jobs.

**Fix (verified live).** `sudo systemctl restart comfyui.service` (9 s to come back, VRAM 14.5 GB → 58 MB).
After the restart the **same stills ran a steady ~26 s each** and the model stayed resident (one Lumina2
load for the whole batch, not one per image). ~6× faster.

**Rule for the perf-tools skill.** Two different ComfyUI slowdowns, different fixes:
| symptom | GPU trace | cause | fix |
|---|---|---|---|
| **load hang** | stuck ~3 %, job never finishes | silent hang mid model-load | restart (only cure); `setperflevel` does nothing |
| **evict-every-job** (this session) | ramps fine, but each job reloads ~19 GB from disk | conservative offload state left by a prior lowvram/partial (Wan) job | restart clears it; then models stay resident |
So: **after running a big Wan (or any lowvram/partial) job, restart ComfyUI before a batch of ACE/Z-Image
work** — otherwise every job pays a full disk-reload. The tell is the log's "Requested to load …" on
*every* prompt when VRAM is nowhere near full.

## Housekeeping

- One `comfyui.service` restart (documented workaround; also the fix under test above). Box left healthy:
  queue empty, perflevel `auto`, GPU idle 3 %. `power_dpm_force_performance_level` untouched this session.
- Reusable: `lantern_songs.py`, `lantern_stills.py`, `build_lantern_video.py` (mirrors of the archie-night
  trio). All under `outputs/lantern-fleet/` (gitignored). Nothing committed — a play session. The
  lore/lyrics/palette are the parts most worth keeping if any.
