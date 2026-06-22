# Discover: 2D asset generation stack

**Status:** completed

## Subject

Local-first 2D image generation for game assets via ComfyUI (host `http://ai2:8188/`), as of
June 2026. Covers: which models/LoRAs are installed and working, their commercial/redistribution
licenses, and what is still needed (angle/style control, alpha, atlas packing) to reach a
repeatable [2d](README.md) harness. The license inventory here is cross-cutting and referenced
by the other tracks.

## Motivation

Decide the default 2D generation engine(s) and the rules under which their output may ship.
Two distinct needs:

1. **Iterate fast now** — best quality/prompt-adherence for prototyping, license-permissive *enough* for internal use.
2. **Ship "clean" later** — assets that are commercially redistributable in an asset pack, where the binding constraint is the **most restrictive link** in the model chain (base + every LoRA + every ControlNet).

## Scope

- In: text-to-image models reachable on `ai2:8188`, their licenses, and the surrounding
  capabilities needed for sprites/textures/backdrops.
- Out: the downstream engine import step (Phaser/Ebitengine), 3D, and deep hardware tuning.
- Source quality gate: licenses are `Confirmed` only when traced to the model's official
  source (HF model card / vendor licensing page); community-finetune licenses that cannot be
  traced are marked `Inconclusive` and treated as prototype-only until resolved.

## Methodology & Sources

- ComfyUI API introspection on `ai2:8188` (`/object_info` for `CheckpointLoaderSimple`,
  `UNETLoader`, `LoraLoader`) — `Confirmed` inventory below.
- Vendor/HF license pages and reporting (see References).
- User-reported working workflows.

## Summary

- **Host reachable** (HTTP 200) and introspectable. `Confirmed`.
- **Two working text-to-image paths** confirmed by the user: FLUX.2 Klein 9B
  (`image_flux2_text_to_image_9b`) and Z-Image Turbo (`image_z_image_turbo`).
- **Clean/commercial engine = Z-Image Turbo (Apache 2.0).** It is the recommended default for
  shippable assets.
- **FLUX.2 Klein 9B (currently installed) is NON-commercial** — excellent for prototyping, but
  not for clean packs. The Apache-2.0 Flux is the **klein 4B**, which is *not* installed.
- **Wan2.2** (installed, image-to-video) is **Apache 2.0** — a clean path for the future
  [vfx](../vfx/) / animation track.
- SDXL community finetunes (Pony/Illustrious/ilustmix) are strong for stylized art but carry
  **murky licenses** — prototype-only until resolved per checkpoint.

## Decisions (2026-06-21)

- **Engine: Z-Image Turbo only — no LoRAs, no finetunes.** The pipeline is Apache 2.0 /
  commercially clean *by construction*, eliminating the most-restrictive-link risk. Alternatives
  are revisited only if Z-Image proves insufficient.
- This **retires** the `StylizedTexture_ZIT` and `zimageTurboBadmilk_v10` license questions —
  neither is used.
- **Control/post stack chosen** (see below): Z-Image ControlNet Union 2.1 (Apache) for
  structure/angle, `rembg` for alpha. No IPAdapter.

## Findings

### Installed inventory on `ai2:8188` (Confirmed)

- **Checkpoints** (`CheckpointLoaderSimple`): `ilustmix_v9`, `prefectPonyXL_v6`,
  `sd3.5_large`, `sd3.5_large_fp8_scaled`, `waiIllustriousSDXL_v170`.
- **Diffusion models** (`UNETLoader`): `flux2Klein_9bBase`, `z_image_turbo_bf16`,
  `zimageTurboBadmilk_v10`, `wan2.2_i2v_{high,low}_noise_14B_{fp16,fp8_scaled}` (video).
- **LoRAs** (`LoraLoader`): `StylizedTexture_ZIT`, `wan2.2_i2v_lightx2v_4steps_{high,low}_noise`.

### License matrix

The **effective output license is the most restrictive artifact in the chain.**

| Artifact (on ai2) | Origin | License | Commercial / clean pack? | Confidence |
|---|---|---|---|---|
| `z_image_turbo_bf16` | Alibaba Tongyi (Z-Image) | **Apache 2.0** | ✅ Yes | Confirmed |
| `zimageTurboBadmilk_v10` | community ZIT finetune | inherits ZIT? own card unverified | ⚠️ verify | Inconclusive |
| `flux2Klein_9bBase` | Black Forest Labs | **FLUX.2-dev Non-Commercial** | ❌ No (prototype only) | Confirmed |
| FLUX.2 **klein 4B** *(not installed)* | Black Forest Labs | **Apache 2.0** | ✅ Yes | Confirmed |
| `sd3.5_large` / `_fp8_scaled` | Stability AI | Stability AI **Community License** | ✅ if org revenue < $1M/yr | Supported |
| `waiIllustriousSDXL_v170` | Illustrious/SDXL finetune | base Illustrious v2.0 = OpenRAIL-M (commercial); v0.1 = fair-ai (anti-monetization); *this* finetune unverified | ⚠️ unclear | Inconclusive |
| `prefectPonyXL_v6` | Pony V6 XL merge | Fair AI Public License 1.0-SD; **bans monetized inference services**; merge terms murky | ⚠️ unclear | Inconclusive |
| `ilustmix_v9` | SDXL anime merge | community, untraced | ⚠️ unclear | Inconclusive |
| `wan2.2_i2v_*` | Alibaba (Wan2.2) | **Apache 2.0** | ✅ Yes | Confirmed |
| LoRA `StylizedTexture_ZIT` | community | untraced | ⚠️ **verify before clean use** | Inconclusive |
| LoRA `wan2.2_i2v_lightx2v_*` | community speed LoRA | likely permissive | ⚠️ verify | Hypothesis |

Note: Pony's "no monetized inference service" clause restricts *offering the model as a paid
service*; selling generated *images* is a greyer area. Either way the merge lineage is
untraced, so treat as prototype-only.

Separate from model license: **AI-generated images may not be copyrightable** in some
jurisdictions (e.g. US) — that affects whether you can *claim* the output, not whether you may
*use* the model. Relevant if asset-pack exclusivity matters later.

### Control & sprite-readiness stack — verified on `ai2` (2026-06-21, API introspection)

- **ControlNet — installed & ready.** Model
  `Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors` (Apache 2.0). Loads via
  **`ModelPatchLoader` → `ZImageFunControlnet`** (native nodes; type `MODEL_PATCH` — *not*
  `ControlNetLoader`, which is empty and irrelevant here). Workflow:
  `image_z_image_turbo_fun_union_controlnet`. Answers the #1 sprite problem: locked angle /
  silhouette / scale. `Confirmed`.
- **Canny — ready (core node).** ComfyUI's built-in `Canny` is present, so canny-conditioned
  generation works **without** any preprocessor pack. Canny is a pure algorithm → cleanest.
- **`comfyui_controlnet_aux` — installed but NOT loaded.** None of its preprocessors register
  (`CannyEdgePreprocessor`, `DepthAnythingV2Preprocessor`, `AIO_Preprocessor`, `DWPreprocessor`
  all absent). Likely needs a **ComfyUI restart**, or the pack failed to import (commonly missing
  `onnxruntime`/`mediapipe`). Needed only for Depth/Pose/HED — **not** a blocker for a Canny-based
  first prototype. `Confirmed` gap.
- **Background removal — node present, NO model installed.** ComfyUI's **native** nodes are on
  `ai2` (`LoadBackgroundRemovalModel` + `RemoveBackground`); only a model file is missing. The
  `Bria*`/`Recraft*` siblings are paid **partner API** nodes — skip. The stale standalone
  BiRefNet node wrapper is a red herring. **Decision: use a BiRefNet (MIT) model** — actively
  maintained (`BiRefNet_dynamic` Mar 2025, `BiRefNet_HR-matting` Feb 2025; matting variant gives
  better soft edges for thin sprite features). Install via either (a) the native loader's model
  folder, or (b) the actively-maintained **ComfyUI-RMBG** pack (1038lab, v3.0.0 Jan 2026, pack
  code MIT) selecting BiRefNet. **Avoid the BRIA RMBG-2.0 model (CC BY-NC, non-commercial)**
  despite the pack name. Do **not** build our own — solved commodity. `Confirmed`.
- **IPAdapter / style-reference — skip** (as decided): immature for Z-Image; use prompt preamble
  + fixed sampler/seed + img2img reference instead.
- **Seamless tiling** (textures) — still to confirm; lower priority than sprites.

### Foundry / Candle — opportunistic notes

(For the future Candle-based [foundry] replacement; capturing what would make it useful for
asset generation.)

- **Current de-facto server is ComfyUI.** Its `/prompt` queue + `/object_info` + node-graph
  workflows are the integration surface this harness will script. A Candle-based foundry that
  wanted to serve asset-gen should match that shape: a job/queue API, deterministic seeds,
  **LoRA hot-loading**, and **ControlNet/img2img/inpaint** conditioning — not just bare t2i.
- **Favor architectures Candle can (or could) serve.** Candle already has Stable Diffusion /
  SDXL and some Flux support; Z-Image and FLUX.2 are newer and likely not yet ported. Worth
  tracking porting effort as a model-selection factor if foundry is to host them.
- **GGUF availability matters to foundry** (it deals in GGUF). Data point: a
  `FLUX.2-klein-base-9B-GGUF` exists (unsloth). Record GGUF availability per model as we go.

## Assessment

- **Feasibility: high.** A clean, fully-commercial 2D path exists today (Z-Image Turbo, Apache
  2.0), with a strong non-commercial quality option (FLUX.2 Klein 9B) for iteration.
- **Biggest risk is licensing drift, not capability.** With community finetunes + LoRAs it is
  easy to silently taint an asset's license. The per-generation license-chain tracking now in
  the findings template is the mitigation; enforce it.
- **Key unknown is the control/post stack** (ControlNet, alpha, tiling), which determines
  whether output is *game-ready* vs *just pretty*. That is the next investigation step.

## Recommendations

1. **Lock the stack: Z-Image Turbo only, no LoRAs/finetunes** — fully Apache 2.0 by construction.
2. **Control/post stack (status):** ✅ Z-Image ControlNet Union (2602 build) + core Canny ready;
   ⚠️ restart ComfyUI to load `comfyui_controlnet_aux` (for Depth/Pose); ❌ install a permissive
   bg-removal model (BiRefNet MIT / U2Net).
3. **Style coherence without adapters:** canonical style preamble + fixed sampler/seed + img2img
   from an approved reference; maintain a "style bible" of approved outputs.
4. **First prototype (new work item):** one DWA hauler sprite end-to-end — crude primitive →
   Canny → ControlNet + Z-Image → `rembg` alpha → trimmed PNG → atlas → rendered in Phaser —
   captured as a filled-in `findings/` doc, to validate the whole harness shape.

## Open Questions

- Why is `comfyui_controlnet_aux` not registering — restart ComfyUI, then check console import errors.
- *(Resolved:)* bg-removal model = **BiRefNet (MIT)**, via native node or ComfyUI-RMBG; avoid BRIA RMBG-2.0.
- Does the Z-Image ControlNet run cleanly on `ai2` (gfx1201) — confirm during the first prototype.
- Candle support status for Z-Image + its ControlNet (foundry relevance).
- *(Resolved/moot:)* `StylizedTexture_ZIT` / `zimageTurboBadmilk` licenses — not used (Z-Image-only).

## References

- Z-Image (Apache 2.0): https://huggingface.co/Tongyi-MAI ; https://www.runcomfy.com/models/tongyi-mai/z-image/turbo
- FLUX.2 klein licensing (4B Apache / 9B non-commercial): https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9B ; https://huggingface.co/black-forest-labs/FLUX.2-klein-4B ; https://bfl.ai/licensing
- Wan2.2 (Apache 2.0): https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B
- Pony Diffusion V6 XL license: https://huggingface.co/LyliaEngine/Pony_Diffusion_V6_XL ; https://ponydiffusion.com/faq
- Illustrious XL v2.0 (OpenRAIL-M): https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0
- FLUX.2-klein-base-9B GGUF: https://huggingface.co/unsloth/FLUX.2-klein-base-9B-GGUF
