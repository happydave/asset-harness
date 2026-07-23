# Wan2.2 i2v on `ai2` — viability reframe + web research (post-WI 1015)

**Date:** 2026-07-23 · **Supersedes the *framing* of** [WI 1013](2026-07-22-wan22-i2v-rocm-fp8.md)
and [WI 1015](2026-07-22-wan22-i2v-fp16-checkpoints.md) findings — the *measurements* stand; the
*decision axis* was wrong.

## The reframe: time is not the gate — quality is

WIs 1002/1013/1015 all judged Wan i2v against **wall-clock** and concluded "not viable" (79 min fp8,
52 min fp16). Owner input 2026-07-23: **these clips will be queued offline with no deadline; 52–79 min
per clip is acceptable as long as the quality is reasonable.** That retires wall-clock as the blocker
and makes **output quality the deciding axis** — which none of the three spikes actually evaluated
properly (each inspected one 4-step-LoRA clip for "is it broken", not "is it good").

**Two prior conclusions this overturns:**

1. **"Not viable"** → **viable, pending a quality verdict.** The load cost is a throughput
   inconvenience for a batch queue, not a disqualifier.
2. **"Prefer fp16" (WI 1015)** → **prefer fp8.** fp16's *only* advantage was speed (52 vs 79 min); with
   time off the table, fp8's **full fit** (13.3 GiB, no spill) beats fp16's **partial `lowvram`
   spill** (26.6 GiB on the 31.9 GiB card, 2.4 GiB offloaded). No-spill should also mean cleaner,
   more predictable sampling. fp16 is retired unless a future need for its (marginal) speed returns.

## Web research (2026-07-23) — two actionable levers

### A. The ~20-min load is likely a known, *possibly fixable* ROCm/ComfyUI interaction

[ComfyUI issue #13730](https://github.com/Comfy-Org/ComfyUI/issues/13730) reports our exact symptom —
model loading stalling at "Requested to load …" on AMD ROCm (RX 7900 XTX, ROCm 7.2), RAM/VRAM/swap
filling — attributed to ComfyUI's dynamic-VRAM / pinned-memory / async-offload machinery interacting
badly with ROCm. Documented mitigations:

- **Launch flags:** `--disable-pinned-memory --disable-async-offload --disable-dynamic-vram
  --reserve-vram 0.5 --cache-none` (also `--use-quad-cross-attention`).
- **Env:** `PYTORCH_HIP_ALLOC_CONF="expandable_segments:True,garbage_collection_threshold:0.75,max_split_size_mb:512"`
  (mirror to `PYTORCH_CUDA_ALLOC_CONF`), `COMFYUI_ENABLE_MIOPEN=0`, `MIOPEN_FIND_MODE=FAST`,
  `unset HIP_HIDDEN_FREE_MEM`.

**Confidence: Hypothesis, not Confirmed.** A related issue,
[#12672](https://github.com/Comfy-Org/ComfyUI/issues/12672) (Wan 2.2 i2v 4–5× slower on *subsequent*
runs, root-caused to ROCm **kernel recompilation** when the VAE reloads and invalidates the shape
cache), reports several of these same flags were **ineffective** for its symptom. Our symptom matches
#13730 (slow on the *loading* phase, first run included) more than #12672 (slow on the *second* run),
so the flags are worth a controlled test — but they are not a guaranteed fix. #12672 also names two
secondary AMD bugs: `WanVAE.encode()` cache sizing uses the decoder count, and `VAE_KL_MEM_RATIO=2.73`
over-estimates VRAM on ROCm (≈1.0–1.3 would be truer) — both plausibly contribute to the offload
thrash we saw.

### B. The poor motion is the 4-step LoRA — and it is fixable

Every quality read so far used the **4-step lightx2v distillation LoRA**, whose own blueprint note
warns of "loss of video dynamics." The community confirms it strongly:
[lightx2v/Wan2.2-Lightning "bad motion"](https://huggingface.co/lightx2v/Wan2.2-Lightning/discussions/5)
— the lightning LoRA "kills motion," worse than Wan 2.1. Our WI 1015 sample (a spinning vortex instead
of the prompted "slow drifting push-in") is the textbook artifact, **not** Wan's quality ceiling. Fixes:

- **Drop the LoRA:** 20-step, CFG ~5–7 (the prototype's `--no-lora` regime). Slower sampling, but full
  motion; and the [Wan 2.2 prompting guides](https://www.veed.io/learn/wan-2-2-prompting-guide) confirm
  camera-motion language ("slow push-in", "slow dolly-in") is respected at full steps/CFG.
- **Or tune the LoRA:** 8 steps (4 high + 4 low), high-noise LoRA strength **0.6–0.8** / low-noise
  **1.0**, CFG **2–3.5** high / **1** low — the community's motion-recovery recipe.

## What to test next (both now affordable — time is not the gate)

1. **Quality spike (the real gate):** on **fp8**, run (a) `--no-lora` 20-step and (b) the tuned 8-step
   LoRA recipe, same opaque planet still + "slow push-in" prompt, and judge motion against the intent.
   No install, no service change — just longer queued jobs. This is what actually decides whether the
   `video` kind lives.
2. **Load-flag spike (throughput, optional):** launch ComfyUI once with the #13730 flags/env and
   re-time a single fp8 clip's load phase. **Needs a `comfyui.service` restart = owner-authorised**,
   and it perturbs a shared box, so it is a deliberate experiment, not a default. Upside: if it works,
   every fp8 workload on the box (not just Wan) loads faster.

## Downstream

- **WI 1004** `kind` budget reopens: **`video` is back as a quality-gated hero-shot option**, on **fp8**,
  pending experiment 1 — no longer a flat "stills only". Recorded in its workitem.
- The rocm7.0 fp8 matmul fix (WI 1013) is untouched and still correct.
