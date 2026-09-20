# Findings: the character-art harness prototype

**Date:** 2026-09-20
**Track:** character-art
**Verdict:** works

## Goal

WI 1611: turn one CSV of characters into VTT-ready tokens through the finishing chain, so the track
has a repeatable pipeline rather than hand-run graphs. Implements
`design-character-art.md`; gated on WI 1599's verdict, which cleared.

## Tooling

- **Container** `localhost/wi1611-comfyui:0.34.6` on `ai2`, built on WI 1600's ROCm image so the
  torch stack is inherited rather than re-solved. Adds Impact Pack (V8.28.3) + Impact Subpack
  (V1.3.5). The shared `comfyui.service` is untouched; the harness runs on loopback 7124.
- **Checkpoints** bind-mounted **read-only** from the shared host — no 7 GB file is duplicated.
- **Generation** `waiIllustriousSDXL_v170`, **finishing** `ilustmix_v9` (design D1), clip skip −2.
- **Detectors** `bbox/yolov8_animeface.pt` (face), `bbox/hand_yolov8s.pt` (hands).
  **No InsightFace** — verified absent from Impact Pack's requirements, not merely unused.
- **Upscale** `RealESRGAN_x4plus_anime_6B`, **matting** ComfyUI **core**.
- Harness at `../prototypes/harness/`.

## The chain, as run

`generate → 2× upscale → face detail → hand detail → house-style → matte → tokens`

One ComfyUI job per stage, deliberately: every stage's output is then an artifact on disk that can
be diffed, which is what makes the inert-detailer check possible at all.

| Stage | Model / node | Settings as run |
|---|---|---|
| generate | WAI Illustrious v17 | 768×1344, dpmpp_2m/karras, 30 steps, CFG 5.0, clip skip −2 |
| upscale | RealESRGAN_x4plus_anime_6B | ×4 by architecture, then `ImageScaleBy` 0.5 → net 2× |
| face detail | `FaceDetailer` + anime YOLO | guide_size 512, denoise 0.45, 20 steps, bbox_threshold 0.5 |
| hand detail | `FaceDetailer` + hand YOLO | same |
| house-style | IlustMix v9, img2img | denoise **0.25** default, 30 steps, **no house-style LoRA** |
| matte | core `LoadBackgroundRemovalModel` + `RemoveBackground` + `JoinImageWithAlpha` | birefnet |
| tokens | Pillow | Roll20 280² PNG; Foundry 400² WebP; 512² rings, no baked border |

**These settings are what was run, not what was tuned.** Nothing was swept; they are reasonable
defaults and the findings claim no more than that.

## Results

**A cast of four through the full chain**, plus a fifth row correctly refused for having no
identity features. 5 stages each, 7 tokens.

**Identity features survive the chain.** Master vs finished, inspected at head-crop magnification:

| Character | Identity features | Verdict |
|---|---|---|
| Tiefling | horn pair; tail with spade; red skin | all intact |
| Dragonborn | snout; scale texture; no human nose | all intact, visibly crisper |
| Half-orc | tusk pair; jaw mass; green skin | all intact, tusks better defined |
| Human (control) | identity; beard; no spurious features | intact, none added |

The chain **sharpened** the two subtle features rather than eroding them.

**Design owner-gate 1 is measured (WI 1598 D1, review F5).** The claim was that IlustMix's weaker
half-orc tusks cannot bite at denoise 0.20–0.30 because the tusks are already fixed in the latent.
Run at both endpoints from the same input: the tusks are present, the same size, in the same place
at **0.20 and 0.30**. **Confirmed** — a low-denoise pass changes surface rendering, not feature
geometry. The remaining half of that gate is aesthetic and is the owner's.

## Three things that differ from what the work item assumed

1. **Matting needs no custom node.** The work item specifies `ComfyUI-RMBG` ≥3.1.0 with BiRefNet
   "Lucida". Core 0.34.6 ships `LoadBackgroundRemovalModel` + `RemoveBackground`, already proven on
   this hardware by WI 1600. Using core removes a custom node from a chain that already carries a
   stale one. Note `RemoveBackground` returns a **MASK**, not a cut-out — `JoinImageWithAlpha`
   applies it as alpha.
2. **`sam2` is optional; `segment-anything` is not.** Impact Pack's `requirements.txt` ends with
   `git+.../sam2`, a heavy unpinned git install. It can be skipped — `core.py` guards it behind
   `importlib.util.find_spec` and prints its own unavailable message. `segment_anything` cannot:
   three modules import it unconditionally at module level. Stripping both breaks the import;
   stripping only `sam2` does not.
3. **The torch constraints rule the ledgers mandate cannot be followed here.** The installed ROCm
   torch is a **local build with no PyPI distribution**, so pip returns `ResolutionImpossible` when
   asked to treat it as a constraint. Install unconstrained and let WI 1600's `check_torch.py`
   assert afterwards — it passed; `ultralytics` and `transformers` did not displace the ROCm wheels.

## Cost

Roughly 4 minutes per character for the full chain on the R9700, dominated by the two detail passes.

## Samples

Artifacts are retained on `ai2` under `~notdave/wi1611/out_final` (69 MB, disposable — the roster
and this recipe regenerate them). The comparison sheets used for the verdicts above are in the
tickets repo at `tmp/1611/`.
