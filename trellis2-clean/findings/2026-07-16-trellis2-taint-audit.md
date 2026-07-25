# TRELLIS.2 — full license taint audit (for the clean-commercial fork)

**Date:** 2026-07-16
**Context:** Fork `github.com/happydave/TRELLIS.2` created to replace nvdiffrast with a clean
differentiable rasterizer. Question: **beyond nvdiffrast, what else in TRELLIS.2 is license-tainted
for commercial use?** Method: static audit of the cloned repo + primary-source license checks. Not
executed; not legal advice.

## Headline

Replacing nvdiffrast is **necessary but not sufficient**. There are **three** non-commercial deps
(nvdiffrast + nvdiffrec + BRIA RMBG-2.0) and one commercial-OK-but-with-obligations dep (DINOv3).
The **core generative weights are MIT**, and the two custom CUDA extensions on the **geometry path
(CuMesh, FlexGEMM) are MIT** — so the geometry lane is clean once the background remover is swapped;
the NC deps all live on the **texturing/PBR + preprocessing** edges.

## Must-replace / remove — non-commercial (blocking)

| Component | Where installed / used | License | Role | Notes |
|---|---|---|---|---|
| **nvdiffrast** | `setup.sh` (NVlabs v0.4.0); `renderers/*`, `trellis2_texturing.py`, `o_voxel/postprocess.py` | NVIDIA Source Code License (NC) | rasterization for texture-bake & mesh rendering | already being replaced |
| **nvdiffrec / renderutils** | `setup.sh` clones `JeffreyXiang/nvdiffrec@renderutils`; used in `renderers/pbr_mesh_renderer.py` (`_nvdiffrec_envlight`) + `utils/render_utils.py` | NVIDIA Source Code License (NC — verbatim: "only may be used…non-commercially…research or evaluation purposes only") | PBR **shading / environment-light integration** | **Co-traveler with nvdiffrast** — the shading half. Your "clean diffrast" effort must cover renderutils too, or the PBR path stays tainted |
| **BRIA RMBG-2.0** | `pipeline.json` default `rembg_model` → `briaai/RMBG-2.0` (via `rembg/BiRefNet.py`) | **CC BY-NC 4.0** (commercial requires a paid BRIA agreement) | input **background removal** (preprocessing) | Easy swap — replace with a permissive segmenter (original `rembg`/U²-Net Apache, InSPyReNet, or BiRefNet's own MIT weights). Not on the model's trained path |

## Commercial-OK but carries obligations (not a blocker — honor the terms)

| Component | License | Obligation |
|---|---|---|
| **DINOv3** (`facebook/dinov3-vitl16-pretrain-lvd1689m`) — the released 4B **image conditioner** (`pipeline.json` → `DinoV3FeatureExtractor`) | Meta **DINOv3 License** — commercial permitted, no MAU cap, no output/training restriction | **"Built with DINOv3" attribution** required; **gated download** (must accept Meta's terms); acceptable-use policy (no military/weapons/etc.); no-reverse-engineering. **Cannot be trivially swapped** — the flow models were trained on DINOv3 features, so changing the backbone means re-training the conditioning |

## Clean / permissive (verified — no action)

- **TRELLIS.2-4B weights = MIT** (HF `cardData.license: mit`). Code = MIT.
- **CuMesh** (`JeffreyXiang/CuMesh`) = **MIT** — used in `representations/mesh/base.py` (geometry).
- **FlexGEMM** (`JeffreyXiang/FlexGEMM`) = **MIT** — sparse-conv backbone + grid_sample (geometry inference).
- **utils3d** (`EasternJournalist/utils3d`) = **MIT**.
- **o-voxel** (in-repo) = MIT; its `third_party/eigen` = MPL2/BSD (permissive).
- Bundled **HDRIs** (`assets/hdri/`) = **CC0** (Poly Haven).
- Stock deps: torch/torchvision (BSD), transformers/timm/kornia/gradio/tensorboard (Apache),
  trimesh/plyfile/torchsparse (MIT), spconv (Apache), flash-attn (BSD), lpips/pandas/zstandard (BSD),
  opencv-headless (Apache), imageio, numpy — all permissive.

## GPL but isolated (not in the inference/generation path)

- **`bpy` / `bmesh` / `mathutils` (Blender, GPL)** — only in `data_toolkit/blender_script/`
  (`dump_pbr.py`, `dump_mesh.py`, `render_cond.py`), i.e. **training-data rendering**, run
  out-of-process. Not imported by the generation pipeline. Keep it out of the shipped product and
  it's a non-issue (same posture as our existing headless-Blender usage).

## What this means for the fork

- **Geometry-only lane is already clean** (MIT weights + MIT CuMesh/FlexGEMM + DINOv3-with-attribution),
  after (a) the one-line `o_voxel/__init__.py` de-eager patch from the [prior trace](2026-07-15-trellis2-hunyuan-nvdiffrast-trace.md)
  and (b) swapping RMBG-2.0 for a permissive background remover. No rasterizer work needed for geometry.
- **The rasterizer work unlocks the clean *textured* lane.** v2's selling point is native PBR; the
  texture *voxels* come from an MIT model (`tex_slat_decoder`), but baking them to a UV texture uses
  **nvdiffrast** and the PBR relight/shading uses **nvdiffrec renderutils** — both NC. So a truly
  clean textured pipeline must reimplement **both** the rasterizer (nvdiffrast) **and** the
  renderutils shading/light-integration (nvdiffrec), not just the former.
- **Two-line taint checklist for the fork to be commercial-clean:** (1) clean diffrast replacing
  nvdiffrast; (2) clean renderutils replacing nvdiffrec; (3) swap `briaai/RMBG-2.0` → permissive
  segmenter; (4) add the "Built with DINOv3" attribution + accept the DINOv3 gate; (5) exclude the
  Blender data_toolkit from anything shipped.

## Not verified / caveats

- Static import + config audit at HF `main` / repo default HEAD, 2026-07-16. Re-verify at integration.
- DINOv3 & RMBG license terms read from primary pages 2026-07-16; both are gated/versioned and can change.
- Whether merely *importing* an NC module without calling it creates obligation is a legal question;
  the reimplementation removes it. Not legal advice.
