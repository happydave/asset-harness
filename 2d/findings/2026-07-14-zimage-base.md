# Findings: Z-Image Base as a selectable engine alongside Turbo

**Date:** 2026-07-14
**Track:** 2d (also touches pbr-materials' shared `gen_albedo` provider)
**Verdict:** works (txt2img) / partial (ControlNet — see F1)

## Goal

Add **Z-Image Base** (`z_image_bf16`) as an opt-in generation engine alongside the existing **Z-Image
Turbo** default, across the 2d track's text-to-image generators, so we have a full-CFG,
working-negative-prompt engine for stylized/anime-adjacent work and as the prerequisite base for a
future self-trained style LoRA (distilled models train poorly). Turbo must stay the default and remain
byte-for-byte unchanged. (asset-harness WI 924; feeds the VTuber-avatar art lane, WI 923.)

## Tooling

- **Base model:** Z-Image **Base** — `z_image_bf16.safetensors` (Tongyi-MAI / Alibaba). Non-distilled.
- **Compared against:** Z-Image **Turbo** — `z_image_turbo_bf16.safetensors` (distilled, the prior default).
- **Shared, unchanged across both:** CLIP `qwen_3_4b.safetensors` (lumina2), VAE `ae.safetensors`,
  `ModelSamplingAuraFlow` shift 3.0; ControlNet `Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps`,
  matte `BiRefNet-HR-matting`.
- **The key difference is a *regime*, not a checkpoint name.** Turbo runs 8 steps / cfg 1.0 /
  `res_multistep` with the **negative conditioning zeroed** (`ConditioningZeroOut`). Base is
  non-distilled and wants a real cfg, more steps, and a **genuinely encoded negative prompt**. The
  generators now carry a `MODELS` preset registry encoding the whole regime per engine:
  - `turbo`: 8 / cfg 1.0 / res_multistep / simple / shift 3.0 / negative zeroed (reproduces prior behaviour exactly).
  - `base`: 20 / cfg 4.0 / euler / simple / shift 3.0 / real `CLIPTextEncode` negative. `--cfg`/`--steps` override.
- **Workflow / scripts:** `2d/prototypes/run_zimage_controlnet.py` and `pbr-materials/prototypes/gen_albedo.py`,
  both gained `--model {turbo,base}` + `--negative/--cfg/--steps`. ComfyUI API graphs on `ai2`.

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Z-Image Base (`z_image_bf16`) | **Apache 2.0** | yes | yes | Tongyi-MAI HF org (Z-Image family) |
| Z-Image Turbo (`z_image_turbo_bf16`) | **Apache 2.0** | yes | yes | (prior findings; unchanged) |
| CLIP / VAE / ControlNet / BiRefNet | Apache/MIT | yes | yes | (prior 2d findings; unchanged) |

- **Effective output license:** **Apache 2.0** — identical posture to Turbo. Adding Base introduces **no**
  new licence link. (Corpus-provenance caveat, per WI 923 research: every image model of this class trains
  on scraped art — a residual exposure no licence label removes; not a licence term.)
- **Safe for a clean/commercial asset pack?** Yes.
- **Notes:** Base is the correct **LoRA-training** base (train on Base, never the distilled Turbo).

## Hardware

- **Machine / GPU:** `ai2` — gfx1201 (AMD R9700 spare), ROCm. Base is plain DiT inference (no CUDA-only
  extensions) — runs on ROCm exactly like Turbo.
- **Timing (768², this run):** Turbo txt2img ~8 s; Base txt2img ~20–22 s (non-distilled, 20 steps). The
  quality/latency trade is the opt-in.

## Inputs

- **Prompt (txt2img side-by-side):** "flat cel-shaded anime character portrait, clean bold lineart, big
  expressive eyes, simple pastel studio background, front view, crisp"
- **Prompt (ControlNet):** the house hauler subject via `inputs/hauler_primitive.png` control image.
- **Seeds:** 77001 (txt2img), 729703840979498 (ControlNet default).
- **Key params:** as per the `base`/`turbo` presets above; provenance is written to `last_run.json`
  (`model` + a `sampling` block) next to every run's outputs.

## Steps

1. `python3 pbr-materials/prototypes/gen_albedo.py --prompt "…anime portrait…" --model base --seed 77001`
   (and `--model turbo`) → side-by-side.
2. Same, `--model base --negative ""` vs default negative, same seed → the negative's effect.
3. `python3 2d/prototypes/run_zimage_controlnet.py --control inputs/hauler_primitive.png --model base`
   (and `--model turbo`) → the ControlNet+alpha pipeline.
4. Compared **decoded pixels** (`Image.convert("RGB").tobytes()` hash), not file bytes — ComfyUI embeds
   the workflow JSON in PNG text chunks, so file SHA is not a valid image-equality signal.

## Result

- **Sample outputs:** [`samples-2026-07-14/`](samples-2026-07-14/)
  - `txt2img_base_anime.png` — **Base txt2img: clean flat cel-shaded anime portrait.** The deliverable's
    point; lands well.
  - `txt2img_turbo_anime.png` — Turbo, same prompt/seed: softer, more photoreal-leaning (confirms
    "Turbo is photoreal-first").
  - `txt2img_base_negEmpty.png` — Base, same seed, empty negative: **visibly different** from the
    default-negative run → the negative prompt acts.
  - `cnet_turbo_hauler_rgba.png` — Turbo ControlNet sprite, cleanly matted. **Unchanged.**
  - `cnet_base_hauler_NOISE.png` — **F1:** Base through the Turbo ControlNet = noise field, no subject.
  - `base_txt2img_last_run.json` — provenance sample.
- **What worked:** Base is a **strong stylized/anime txt2img engine** with working negatives and real CFG
  — exactly the capability Turbo lacks. Turbo path provably unchanged (byte-identical graph; matte
  behaviour identical). Negative + CFG demonstrably act (pixel-verified). Provenance records the engine.
- **What failed — F1:** the **Turbo-trained Fun-ControlNet-Union patch does not transfer to the Base
  checkpoint.** Base through the ControlNet produces an undenoised noise field → BiRefNet finds no
  subject → **empty (100% transparent) RGBA**. Persists at Base's 20-step/cfg-4 regime *and* at the
  patch's native 8-step/cfg-1 schedule, so it is the patch↔checkpoint pairing, not the sampling params
  (Base txt2img with the same preset is clean, isolating the ControlNet as the cause).

## Repeatability

- Deterministic given seed (a re-run at the same seed/negative produced pixel-identical output — also
  visible as a ComfyUI KSampler cache hit). Style-consistent. No manual cleanup for txt2img.

## Engine-selection decision (recorded)

- **All existing batch generators stay on Turbo by default.** Their shipped DWA fleets are
  reproducible-by-seed and must not silently change; Base is **opt-in** (`--model base`).
- **Use Base for:** new stylized/anime-adjacent **txt2img** work, and as the **LoRA-training base**.
- **Use Turbo for:** speed, photoreal-ish subjects, and — because of F1 — **all ControlNet-driven sprite
  work** (the structured hauler/module/miner/celestial pipeline). Base is a txt2img engine in this stack.

## Next

- **F1 → optional future work item, only if structured Base sprites are ever needed:** source or train a
  **Base-matched ControlNet** (the current patch is Turbo/8-step-specific), or drive Base structure by a
  non-ControlNet method (img2img/inpaint/regional). Not needed now — Turbo already owns the ControlNet
  sprite path and Base's value is txt2img.
- **Z-Anime** (Apache-2.0 anime finetune of Base, from WI 923 research) is **not installed on `ai2`**, so
  it was not trialled here — deferred; needs a server-side model add first (out of scope for WI 924).
- **Tune Base defaults** (steps/cfg/sampler) against more prompts as stylized work ramps; 20/4.0/euler is
  a solid starting point, recorded in the preset and overridable via `--cfg`/`--steps`.
