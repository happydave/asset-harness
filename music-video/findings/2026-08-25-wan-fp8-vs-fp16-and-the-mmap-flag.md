# Wan2.2 i2v: fp8 vs fp16 under the 2/2 split — and the flag that matters more (WI 1161)

**Date:** 2026-08-25 · **Box:** `ai2` (R9700 gfx1201, 32.6 GB VRAM, 91 GB host RAM) · **Verdict:**
adopt **fp8**; and keep **`--disable-mmap`** on, which is worth more than the dtype

## Headline

| Config | Per clip (1280×720 × 33 f) | Stage load | Residency | VRAM | Host RAM |
|---|---|---|---|---|---|
| **fp8**, `--disable-mmap` on | **127 s** | 6 s | `loaded completely` | 20.0 / 32.6 GB | ~33 / 91 GB |
| fp16, `--disable-mmap` on | 384 s | 4–112 s | **`loaded partially`**, 33–36 lowvram patches | 32.0 / 32.6 GB (full) | **~69 / 91 GB** |
| fp8, `--disable-mmap` **off** | ~75 min (extrapolated) | **35.8 min** | `loaded completely` | — | — |

fp8 is **3.0×** faster than fp16. The mmap flag is **~360×** on a checkpoint load. They compose.

## The mmap flag was off, and that is the bigger story

`ai2`'s `--disable-mmap` drop-in (from [WI 1054](../../../../tickets/docs/pending/1054-ai2-comfyui-wan-mmap-load-hang/investigate.md))
was renamed `.disabled` on **2026-08-05** because with the **fp16** pair it drove host RAM near full.
With it off, every load pays a per-tensor page-fault stall:

| Artifact | flag off | flag on |
|---|---|---|
| umt5 text encoder (6.4 GB) | **341 s** | **<1 s** |
| Wan high-noise UNET fp8 (13.6 GB) | **35.8 min** | **6 s** |

Same file, same box, same day — one flag.

**This corrects a standing attribution.** WIs 1013/1015 measured "~36 min per checkpoint" and attributed
it to **fp8 weight preparation at load time**, concluding that fp8 was load-bound and that video on `ai2`
was impractical. It was the mmap stall — the same root cause WI 1054 found behind the 341 s text-encoder
"hang", scaled to a larger file. **fp8's load cost is not a property of fp8.**

## The residency hypothesis is refuted

The [clamor-motion session](../prototypes/outputs/clamor-motion/SESSION.md) proposed that fp8, at 13.6 GB
per stage, would let **both** experts stay resident and remove the swap. It does not:

- `usable` VRAM resets to ~25.6 GB when the second stage loads — the first was **evicted**, as with fp16.
- VRAM sampled mid-sampling is **20.0 GB**: one UNET (13.6) + text encoder (6.4) + VAE (0.24). Two UNETs
  would be ~27.5 GB before the encoder.

fp8 wins for a different reason: it **fits without spilling**. fp16 reports `loaded partially` with
~1.8–1.9 GB offloaded and 33–36 lowvram patches, which costs sampling throughput too — the same two
sampler steps took ~3 min under fp16 against **47 s** under fp8.

## Quality — acceptable, with a verified control

Same still (`tc_04_the_horde.png`), seed 302, prompt and graph identical; only the UNET filenames differ.

- fp8 vs fp16: **SSIM mean 0.939** (min 0.920 last frame, max 0.983 first — divergence accumulates from
  a shared frame 0). Motion preserved: mean scene score **0.01585** vs **0.01581**.
- **Determinism control:** today's fp16 vs the 2026-07-28 delivered clip — **SSIM 1.0 on all 33 frames**,
  identical motion statistics. The pipeline is deterministic across a month, a restart and the flag flip,
  so the fp8 difference is **dtype**, not drift.
- **Inspected directly:** both coherent throughout — no pop-ins, morphing, scene drift or hallucinated
  text. fp8 is marginally softer with slightly more haze and less figure separation. Small, and unlikely
  to read in a ~2 s accent shot.

**Evidence base:** one shot, deliberately the hardest content type available (a moving crowd). A softness
difference that does not matter on a crowd could matter on a close subject; treat the quality result as
established for scene-scale shots and provisional for character close-ups.

## Consequences

- **Recipe changes to fp8** in [`skills/prompting-wan-i2v/SKILL.md`](../../skills/prompting-wan-i2v/SKILL.md),
  with `--disable-mmap` recorded as a prerequisite rather than an optimisation.
- **`--highvram` (WI 1042) needs its premise revisited**: reloads are cheap once mmap is off, stages are
  evicted regardless, and there is no headroom to pin two UNETs.
- **Clip chaining (WI 1160) gets cheaper** — at ~127 s/clip, multi-link continuous shots are minutes.

Evidence: [`samples-2026-08-25-fp8-vs-fp16/`](samples-2026-08-25-fp8-vs-fp16/) — both clips, the stacked
frame-32 comparison, the two `compare.json` measurement sets (including the determinism control), and the
per-run timing records.

Full design, execution log and reflect: [WI 1161 spike.md](../../../../tickets/docs/pending/1161-ah-wan-fp8-two-stage-speed/spike.md).
