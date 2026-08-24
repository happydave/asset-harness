# Lantern Fleet — "Between the Lights" (chaining session) — 2026-07-29

The challenge: **two 6 s clips where clip 2 continues from clip 1's cleaned-up last frame, so they read
continuous.** Proven, and built into a new Lantern Fleet video. Also fixes last session's "clip followed
by its own source still" issue. Ends with an ai2 GPU-hardware blocker (below) that a ComfyUI restart
could not fix.

## The chaining technique — works

1. **clip 1**: 6 s (97 f @ 16 fps) two-stage fp16 Wan i2v from a still (the `wan2.2-test` recipe), at
   **832×480** (6 s at 720p OOMs — 97-frame latents pushed VRAM to 33.3/34 GB even at 480p).
2. **clean the last frame**: extract clip 1's final frame, then a **content-preserving** ffmpeg pass —
   `hqdn3d` (light denoise) + `unsharp` (moderate luma) + a touch of contrast/saturation. Crucially this
   **sharpens without moving content**, so clip 2's first frame still matches clip 1's last.
3. **clip 2**: 6 s from the cleaned frame, same recipe, prompt continues the motion.
4. **concat**: because i2v reproduces its start frame at frame 0, clip 2's frame 0 ≈ cleaned(clip 1
   last) — so the seam is **content-continuous** (no positional jump). The only seam artifact is a faint
   acuity lift where the cleaned frame begins, plus i2v's inherent slight motion-restart; a short
   crossfade hides both.

Verified on a 12 s skiff-flight (`chain_test/chained.mp4`): scene-scores smooth (~0.005–0.014), seam
filmstrip continuous. **Cost: ~9 min per 6 s clip** (fp16 loads dominate). Driver: stock
`generate_clip.py --fp16 --frames 97 --width 832 --height 480`.

**Cleanup method note:** a low-denoise img2img (Z-Image/realifier) would restore more detail but shifts
content and would break the seam. For continuity, the content-preserving ffmpeg pass is the right call.
No upscale model (RealESRGAN etc.) is installed on ai2 — a follow-up if we want stronger restoration.

## The video: "Between the Lights"

A third [Lantern Fleet](../lantern-fleet/lore.md) song — the **long solo crossing** between two islands —
scored to the continuous flight. Song/lore in [lyrics.md](lyrics.md).

- **Song**: turbo sweep, best by Audiobox CE = **seed802** (CE 7.92, PQ 8.44). −1 dBTP, not truncated.
- **Spine**: the 12 s chained skiff-flight opens the video (single video shot, preserving the continuous
  motion; the internal 6 s seam is the technique above).
- **Body**: 8 stills with Ken-Burns. **Beat-map fix**: no motion clip is ever followed by its own start
  still. `lamp_01_skiff` (the flight's source frame) is deliberately **excluded** from the still set.
- **Output**: `video/crossing_between_the_lights.mp4` — 75.0 s, 1280×720 h264+aac, verified.

## ai2 GPU blocker (unresolved — needs owner)

Midway through the crossing **stills**, ai2's GPU degraded and I could not recover it in-session:

- **Symptom**: GPU0 **SCLK pinned at ~41 MHz** (idle clock) under load, GPU% ~3, power ~24 W. Jobs either
  crawl (stills went 115 → 165 → 202 s, climbing) or wedge outright (job "running", GPU flat idle).
- **Not fixed by `setperflevel high`**: power rose (24→54 W) and MCLK ramped, but **SCLK stayed at
  41 MHz** — the core clock will not ramp. (Consistent with archie-night: forcing perf raises power, not
  the shader clock.)
- **Not fixed by ComfyUI restart**: restarted twice; the wedge/slow state returned within a few jobs.
  This is therefore **not** the software model-eviction issue — it's a **GPU power/clock state**, likely
  residue of the server incident earlier today.
- **Likely fix**: a full **ai2 reboot** (or an amdgpu-level GPU reset). I did **not** reboot — that's the
  owner's call, and the box may be in use.
- **Left as-found**: `power_dpm_force_performance_level` reset to `auto`; ComfyUI running; nothing queued.

> **RESOLVED 2026-08-13**: ai2 recovered (no reboot needed — the wedge cleared on its own; 20-day
> uptime, WI 1065 ran full-speed generation 2026-08-10). The 5 missing `bl_*` stills were regenerated
> (seed 701, ~30 s each, healthy ramp) and the video **rebuilt as the fully bespoke cut** — the
> lantern-fleet placeholder stills are no longer used. The paragraph below is kept as history.

**Workaround used to still deliver the video**: 3 of 8 crossing stills generated before the wedge
(`bl_01_striker_tiller`, `bl_02_light_behind`, `bl_03_cloud_sea`); the other 5 shots reuse existing
`lantern-fleet` stills (same universe/palette) — `lamp_02_fleet`, `lamp_04_striker`, `lamp_03_beacon`,
`lamp_05_lifting`, `lamp_08_oilchild`. The song, the 12 s flight, and the build needed no further GPU.

## Reusable / follow-ups

- `crossing_songs.py`, `crossing_stills.py`, `build_crossing_video.py`; the chained flight is under
  `../lantern-fleet/chain_test/` (`clip1.mp4`, `clip2.mp4`, `last_clean.png`, `chained.mp4`).
- **Chaining is ready to productize**: a small driver (gen 6 s → ffmpeg-clean last frame → gen 6 s → concat)
  would make arbitrary-length continuous shots. Worth a WI alongside the fp8-two-stage speed idea from the
  clamor-motion session.
- Regenerate the 5 reused shots as proper `bl_*` crossing stills once ai2's GPU is healthy, for a fully
  bespoke cut.
- All under `outputs/lantern-crossing/` (gitignored). Nothing committed — play session.
