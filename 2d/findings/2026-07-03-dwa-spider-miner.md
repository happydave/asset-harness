# Findings: DWA spider-miner body/head sprite

**Date:** 2026-07-03
**Track:** 2d
**Verdict:** works

## Goal

Produce the DWA WI 801 **spider-miner** body/head sprite for DWA WI 813 — a top-down,
orientation-neutral hub (central rock-crusher maw, hexagonal armored body, eight leg-root sockets
around the rim) that DWA WI 808 will swap in for the procedural `generateAutoMinerTexture`
silhouette. The miner's legs stay procedural in-engine (rig WIs 805–807), so only the body/head is
sourced here. Several candidates were generated for Dave to choose from.

## Tooling

- **Base model:** Z-Image Turbo (`z_image_turbo_bf16.safetensors`), CLIP `qwen_3_4b` (lumina2),
  VAE `ae.safetensors`.
- **ControlNet:** Z-Image Fun ControlNet Union 2.1 (`Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors`)
  via `ModelPatchLoader` + `QwenImageDiffsynthControlnet`, driven by core `Canny`.
- **Background removal:** native `LoadBackgroundRemovalModel` + `RemoveBackground` with
  `BiRefNet-HR-matting.safetensors` (mask inverted so the subject is opaque).
- **Workflow / scripts:** `2d/prototypes/run_zimage_controlnet.py` (graph builder),
  `2d/prototypes/generate_spider_miner.py` (candidate sweep + contact sheet),
  `2d/prototypes/make_primitives.py::spider_miner` (control primitive),
  `2d/prototypes/build_atlas.py` (trim + atlas). No LoRAs, no finetunes.

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Z-Image Turbo | Apache 2.0 | yes | yes | huggingface.co/Tongyi-MAI |
| Z-Image Fun ControlNet Union 2.1 | Apache 2.0 | yes | yes | (Z-Image Fun ControlNet) |
| BiRefNet-HR-matting | MIT | yes | yes | BiRefNet (MIT) |

- **Effective output license:** Apache 2.0 (most-restrictive link across an all-Apache/MIT chain).
- **Safe for a clean/commercial asset pack?** Yes — clean by construction (no LoRAs/finetunes).
- **Notes:** AI-generated images may not be copyrightable in some jurisdictions (US); affects
  whether the output can be *claimed*, not whether the model may be *used*.

## Hardware

- **Machine / GPU:** `ai2` — gfx1201 (R9700 spare card).
- **Stack:** ROCm; ComfyUI serving at `http://ai2:8188/`.

## Inputs

- **Prompt:** `STYLE` anchor (top-down orthographic game sprite, industrial used-future space
  vessel, weathered painted steel, gunmetal grey with rust-orange hazard accents, soft even
  lighting, clean readable silhouette, isolated on plain white) + subject: "a radially symmetric
  asteroid-mining drone seen from directly above, a hexagonal armored hub with a central rotary
  rock-crusher maw ringed by teeth, eight short leg-mount sockets spaced evenly around the rim,
  compact and squat, no front or rear, no cockpit".
- **Seeds:** base `729703840979498` (shipped-fleet family) + `i·101` for i in 0..5 →
  candidates cand00..cand05. **Chosen: cand05, seed `729703840980003`.**
- **Key params:** 8 steps, cfg 1.0, `res_multistep` / `simple`, AuraFlow shift 3.0, ControlNet
  strength 0.85, control primitive scaled to 1024, Canny thresholds 0.1 / 0.32.

## Steps

1. `python make_primitives.py spider_miner inputs` — writes the radially-symmetric control primitive.
2. `python generate_spider_miner.py --count 6` — uploads the primitive, sweeps 6 seeds through the
   Z-Image + ControlNet + BiRefNet graph, writes RGBA/opaque/canny per candidate, a manifest, and
   `contact_sheet.png`.
3. Pick a candidate (cand05), then
   `python build_atlas.py --manifest outputs/spider_miner/chosen_manifest.json --indir outputs/spider_miner --outdir outputs/spider_miner/atlas --name dwa_miner --max-dim 256`
   → atlas PNG + Phaser JSON, single frame keyed `autominer` (= DWA `MINER_TEXTURE_KEY`).

## Result

- **Sample output(s):** `2d/findings/samples-2026-07-03-spider-miner/` — the chosen sprite
  (`autominer.png`, 256×256), the atlas (`dwa_miner.png` + `dwa_miner.json`), and the
  `contact_sheet.png` of all six candidates. (Bulk `outputs/` stay git-ignored per repo convention.)
- **What worked:** All 6 candidates read as coherent radially-symmetric crusher hubs with rim
  sockets in the fleet palette — the non-directional subject + a symmetric control primitive held
  the "no front" property, and the shared STYLE anchor + fleet seed kept them coherent with the
  hauler. cand05 has a deep turbine maw and sockets on short mount struts (best leg-attachment read).
- **What failed / artifacts:** BiRefNet left faint sub-threshold alpha specks on cand00/01/04
  (full-frame alpha bbox despite transparent borders/corners) — cosmetically harmless but they
  defeat a naive `getbbox()` trim. Selecting a clean candidate (cand05) side-stepped it.

## Repeatability

- Deterministic given seed (fixed sampler/seed/params). Style-consistent across the sweep via the
  STYLE anchor + fleet seed family. No manual cleanup needed for the chosen sprite; a small alpha
  threshold in `build_atlas.trim_and_fit` would make trimming robust to the speck artifact.

## Next

- DWA WI 808 integrates `autominer` (replace the generated texture with the atlas frame; legs stay
  procedural).
- Optional harness hardening: add an alpha-threshold trim to `build_atlas.py` so speckly candidates
  trim cleanly (Reflect item).
