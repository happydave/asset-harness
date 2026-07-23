# Wan2.2 i2v on `ai2` — fp16 checkpoints vs fp8_scaled (WI 1015)

**Date:** 2026-07-22 · **Box:** `ai2`, R9700 (gfx1201, 31.9 GiB), ComfyUI torch **2.10.0+rocm7.0**
· **Sibling:** [`2026-07-22-wan22-i2v-rocm-fp8.md`](2026-07-22-wan22-i2v-rocm-fp8.md) (the fp8 run this
challenges)

## Question

WI 1013 fixed the fp8 `_scaled_mm` matmul but found Wan clips still take ~79 min, and attributed the
cost to **loading** the fp8 checkpoints (~36 min each), which it read as fp8 weight-prep. If that were
the whole story, the **fp16** checkpoints — no fp8 weights to prepare — should load fast and make video
viable. This is the test of that hypothesis.

## Method (controlled — only the UNET dtype changed)

Identical to the fp8 run except the two UNETs: `wan2.2_i2v_{high,low}_noise_14B_fp16.safetensors`
(26.6 GiB each) in place of the `_fp8_scaled` pair (13.3 GiB each). Same 640×640 / 81f @ 16fps /
4-step LoRA / seed 901 / stock negative / opaque `planet_opaque.png`. Client:
[`prototypes/generate_clip.py --fp16`](../prototypes/generate_clip.py). The umt5 text encoder stays
fp8 (no fp16 copy on the box) — a constant across both runs, so it does not confound the comparison.

## Result — fp16 is faster but still not viable

**`Prompt executed in 00:52:26`** for one 5.06 s clip (vs **79 min** fp8). Phase timeline from
`journalctl` ([`samples-2026-07-22-wan/fp16_journal_phases.txt`](samples-2026-07-22-wan/fp16_journal_phases.txt)):

| Phase | fp16 | fp8 (WI 1013) |
|---|---|---|
| TE load (fp8, constant) | ~5m47 | 5m38 |
| **high-noise UNET load** | **19m46** — partial, 2.4 GiB offloaded | 35m48 — full |
| stage-1 sampling | ~3m29 | ~1min |
| **low-noise UNET load** | **19m47** — partial, 2.4 GiB offloaded | 35m48 — full |
| stage-2 sampling | ~3m16 | ~1min |
| VAE decode + mux | ~11s | ~11s |
| **Total** | **52m26** | 79m |

At ~5 s/shot, a 3-minute music video ≈ 36 clips ≈ **31 hours**. Not viable.

## Two things this overturns

**1. The load bottleneck is mostly dtype-INDEPENDENT — WI 1013's root cause was only partly right.**
fp16 loads in 19m47 vs fp8's 35m48. The ~16-min gap *is* the fp8 weight-prep WI 1013 named (real), but
it is not the dominant term: a **~20-min-per-checkpoint load path that has nothing to do with fp8**
dominates both. A 26.6 GiB model already sitting in the host page cache (91 GiB RAM, 53 GiB
buff/cache) should reach VRAM in ~1 min; 20 min is pathological. **Root cause unknown and out of scope
here** — candidates: the ROCm/gfx1201 host→device transfer path (the card already needs `pcie_aspm=off`
and other quirks), ComfyUI lowvram streaming, or PCIe-link degradation.

**2. 26.6 GiB fp16 does not fit the 31.9 GiB card.** Both stages loaded **partially** in `lowvram`
mode — `24862 MB loaded, 2390 MB offloaded, lowvram patches: 45`. ComfyUI reports ~25.1 GiB usable
after reserving activation headroom, ~1.5 GiB short of the model. The live VRAM climb was slow and
linear (~0.9 GiB/min), the signature of lowvram streaming rather than a bulk copy. So fp16 buys a
faster-but-still-huge load *and* a permanent spill.

## Output is fine — the blocker is time+fit, not quality

Frames 0/40/80 ([`samples-2026-07-22-wan/fp16_frame{00,40,80}.png`](samples-2026-07-22-wan/),
clip [`fp16_clip_s901.mp4`](samples-2026-07-22-wan/fp16_clip_s901.mp4)): coherent planet + a small
moon, concentric swirling motion, colour drifting teal→gold. **No invented background, no hallucinated
title text** — the opaque-input rule ([WI 1002 F-5](2026-07-22-wan22-i2v-rocm-fp8.md)) held again. The
motion is a spin/vortex rather than the prompt's "gentle push-in", but that is a prompt/model trait,
not a dtype one. A usable clip means the not-viable verdict is purely about cost.

## Verdict & downstream

- **fp16 is not a remedy for video on `ai2`.** WI 1004 stays **stills + Ken Burns** — now confirmed
  against *both* dtypes, so "no Wan clips from `ai2`" is settled, not pending.
- **The one remaining lever is the ~20-min load path itself**, not the dtype. If a targeted
  micro-benchmark (bare `safetensors`→VRAM, no sampling) shows the transfer is fixable (driver, PCIe,
  or a ComfyUI setting), video could become viable at either dtype. That is an Investigate/Spike of its
  own — recommended to the owner, not filed here.
- **Even with the load fixed, fp16 would still run lowvram** on this card unless resolution/frames drop
  — a secondary reason to prefer the fp8 checkpoints if the load path is ever solved.
