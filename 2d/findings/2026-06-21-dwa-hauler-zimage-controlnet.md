# Findings: DWA hauler sprite — Z-Image + Fun ControlNet + alpha

**Date:** 2026-06-21
**Track:** 2d
**Verdict:** works

## Goal

Validate the whole 2D harness shape end-to-end on the clean-license stack: a structured,
angle-locked game sprite (a Deadweight Acquisitions cargo hauler) generated from a crude
primitive, then cut to transparency — produced entirely by script against `ai2`'s ComfyUI API.

## Tooling

- **Base model:** `z_image_turbo_bf16` (Z-Image Turbo), text encoder `qwen_3_4b` (CLIPLoader
  type `lumina2`), VAE `ae.safetensors`.
- **LoRA(s) / ControlNet / adapters:** ControlNet patch
  `Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps` applied via
  `QwenImageDiffsynthControlnet` (Canny condition). No LoRAs, no finetunes.
- **Workflow / nodes:** `samples-2026-06-21-hauler/workflow_api.json` (the exact API graph sent).
  Sampling: `ModelSamplingAuraFlow` shift 3 → `KSampler` 8 steps, cfg 1, `res_multistep` /
  `simple`, denoise 1. Latent sized from the control image via `GetImageSize`.
- **Other software:** native `LoadBackgroundRemovalModel` + `RemoveBackground` (BiRefNet),
  `InvertMask`, `JoinImageWithAlpha`. Driver script `2d/prototypes/run_zimage_controlnet.py`;
  control primitive from `2d/prototypes/make_hauler_primitive.py` (PIL).

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Z-Image Turbo | Apache 2.0 | yes | yes | Tongyi-MAI |
| Z-Image Fun ControlNet Union | Apache 2.0 | yes | yes | alibaba-pai |
| Canny (core node) | algorithm | yes | yes | — |
| BiRefNet-HR-matting | MIT | yes | yes | ZhengPeng7 / 1038lab |

- **Effective output license:** Apache 2.0 (most restrictive link).
- **Safe for a clean/commercial asset pack?** yes.
- **Notes:** entire chain is Apache/MIT by construction; no per-asset license drift to track.

## Hardware

- **Machine / GPU:** `ai2` host — AMD R9700 (**gfx1201**).
- **Stack:** ROCm ComfyUI. **Confirmed: Z-Image + Fun ControlNet run cleanly on gfx1201.**
  8-step turbo generation completed well within timeout; no CUDA-only-op failures.

## Inputs

- **Prompt:** "top-down orthographic game sprite of an industrial space cargo hauler, armored
  greebled hull, side cargo pods, three engine nozzles with faint glow, weathered painted metal,
  clean readable silhouette, centered, isolated on a plain solid white background, soft even
  studio lighting, crisp detail, high quality concept art"
- **Negative:** `ConditioningZeroOut` of positive (turbo, cfg 1 — negative inert).
- **Seed:** 729703840979498
- **Key params:** ControlNet strength 0.85; Canny low 0.1 / high 0.32; 1024×1024.

## Steps

1. `make_hauler_primitive.py` → crude gray hauler silhouette with panel lines (`01_primitive.png`).
2. `run_zimage_controlnet.py` uploads it, builds the API graph, queues on `ai2`, polls
   `/history`, downloads results. Repeatable; persists `last_graph.json` + `last_run.json`.

## Result

- **Sample outputs** (`samples-2026-06-21-hauler/`): `01_primitive.png` → `02_canny.png`
  (clean edges) → `03_opaque.png` (final render) → `04_rgba.png` (alpha cutout).
- **What worked:** Z-Image followed the ControlNet structure faithfully — nose, glowing
  cockpit, two side cargo pods, panel-lined hull, 3-nozzle engine block — in convincing
  weathered metal. Silhouette matches the primitive (angle/scale locked). BiRefNet matting
  gave a clean edge cut (final alpha ≈ 83% transparent / 16% opaque subject).
- **What failed (then fixed):** `RemoveBackground`'s mask polarity is inverted vs
  `JoinImageWithAlpha` — first run cut the ship instead of the background. Fixed permanently
  by inserting `InvertMask`. (This confirms the polarity caveat from `discover.md`.)

## Repeatability

Deterministic given seed; the exact graph is saved per run. Style is *not yet* anchored — this
is one ad-hoc prompt, not a locked house style, so a second asset would not yet match a fleet.

## Next

- **Style anchor:** define a canonical style preamble + fixed sampling so a *set* (hauler,
  miner, station parts) is visually coherent; test by generating 2–3 ships and comparing.
- **Downstream (still missing):** auto-trim to content bbox, downscale to game resolution,
  texture-atlas packing, and import into the DWA Phaser project — the remaining half of the
  harness.
- Sweep ControlNet strength / Canny thresholds for the best structure-vs-creativity balance.
- Consider folding `InvertMask` awareness into a reusable bg-removal sub-workflow.
