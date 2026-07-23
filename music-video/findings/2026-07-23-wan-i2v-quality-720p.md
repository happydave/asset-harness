# Wan2.2 i2v quality on real Clamor stills at 720p (WI 1018) — video is viable

**Date:** 2026-07-23 · **Box:** `ai2` (fp8, torch 2.10.0+rocm7.0) · **Builds on** the
[viability reframe](2026-07-23-wan-on-ai2-viability-reframe.md) (time is not the gate; prefer fp8;
the LoRA kills motion).

## Verdict: GO for a `video` hero-shot in WI 1004 — fp8, no-LoRA 20-step, 720p

Two storytelling stills (Z-Image base, 1280×720, opaque) → fp8 Wan2.2 i2v (no-LoRA 20-step) produced
**coherent, on-brief motion on both content types**:

- **Character** (lantern-lit scavenger): a real cinematic push-in with a coherent character walk —
  stands, steps forward, mid-stride by the end. No vortex, no hallucinated text.
- **Scene** (zombie horde on a lit barricade): the crowd advances under a drifting camera; many figures
  stay coherent across frames — the harder case, and it holds.

Frames + clips in [`samples-2026-07-23-wan-quality/`](samples-2026-07-23-wan-quality/). Stills generated
by the new opaque [`generate_still.py`](../prototypes/generate_still.py) (Z-Image base, no matte).

**This settles the reframe's open question:** the WI 1015 vortex was the **4-step lightx2v LoRA**, not
Wan. Dropping it → production-quality motion.

## 720p fits fp8 cleanly (resolution answered)

Both runs, both stages: the UNET `loaded completely … full load: True` — **no `lowvram`, no host
offload** (contrast fp16, which spilled at 640×640). fp8 (13.6 GiB) + 720p latents fit the ~17 GiB
usable budget. **1280×720 is the resolution.** 480p is unnecessary; 1280×960 is off Wan's native grid
and untested.

## The load is a once-per-SESSION cost, not per-clip (corrects WI 1002/1013/1015)

The big surprise. Run #2 reused run #1's model, so both UNET loads took **1 second** (warm cache) vs
run #1's ~14 min cold. So:

| | Run #1 (cold) | Run #2 (warm) |
|---|---|---|
| UNET loads (2) | 13m49 + 14m05 | **1 s + 1 s** |
| sampling (2) | 36m28 + 36m22 | 36m27 + 36m22 |
| **Total** | **1h48m** | **1h13m** |

**The ~14–36 min load is a cold, once-per-session tax; a batch of N clips pays it once, then each clip
is sampling-only.** WI 1004's ~36-clip song is far cheaper than a single cold clip implied — the
per-clip fear from the earlier spikes was a session cost misread as per-clip. (Also: cold-load time is
*variable* — 14 min here vs 35 min in WI 1013 — consistent with ComfyUI's per-run VRAM-unload
behaviour differing, ComfyUI-ROCm #12672.)

## Known quality gap → WI 1019 (not a blocker)

The clips are **framey** (16 fps is Wan's native rate) and a touch **soft**. Two levers, both without a
new model:
- **RIFE interpolation** to ~32 fps (post, no regen).
- **Better settings** — this run used **euler/simple, cfg 3.5, 20 steps**, which community reports as
  suboptimal for Wan; **res_multistep/sgm_uniform, cfg ~5, 30 steps** are recommended. Time is free
  (offline batch), so 30 steps is affordable.

These are **WI 1019** (settings + interpolation; in the `tickets` backlog). A **Qwen-Image-Edit
realifier** (Apache-2.0 — clean still artifacts like the character's off-hand object) and a **per-model
prompting skill** are deferred to their own follow-ups.

## Also learned

- **Per-shape MIOpen kernel compile:** the first 1280×720 generation paid ~8 min one-time kernel
  compilation; the next same-shape gen was ~27 s. Budget a one-time tax per new resolution on this box.
- **Two orchestration bugs (mine), recovered:** a client `--timeout` shorter than a cold no-LoRA run
  left a finished clip undownloaded (recovered from ComfyUI `/history`), and a brittle batch wait-loop
  wedged. Fixes: long timeouts + file-polling waiters. No result lost.

## Recommended settings (current best, pending WI 1019)

- **Stills:** Z-Image base, 1280×720, opaque (no matte), cfg 4 / 20 steps / euler / shift 3.
- **Video:** fp8 Wan2.2 i2v, **no-LoRA**, 720p, 81 f. Current: euler/simple, cfg 3.5, 20 steps, shift 5,
  16 fps. **WI 1019 will tune** sampler→res_multistep/sgm_uniform, cfg→~5, steps→30, + RIFE→~32 fps.
