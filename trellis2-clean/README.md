# Track: trellis2-clean

**Status:** 🟡 **Active — fork created, audit done** (2026-07-16). Goal: make Microsoft's **TRELLIS.2**
(4B image→3D; MIT weights + code) usable for **commercial** game-asset generation by removing its
non-commercial NVIDIA dependencies. Fork: `github.com/happydave/TRELLIS.2`. Tracked as **WI 950**.

## Why this track exists

TRELLIS.2's weights and code are MIT, and the geometry-path CUDA extensions (CuMesh, FlexGEMM) are
MIT — but the shipped pipeline pulls in NVIDIA **non-commercial** components (nvdiffrast, nvdiffrec)
on the texturing/PBR path and a CC-BY-NC background remover. The taint is on the edges, not the core,
which makes a clean fork realistic.

## The two lanes

- **Geometry-only (nearly free):** one-line `o_voxel/__init__.py` de-eager patch (so importing the
  geometry decoder doesn't transitively require nvdiffrast) + swap the background remover → an
  MIT-clean mesh. No rasterizer work.
- **Textured (the real work):** reimplement **both** the rasterizer (replacing nvdiffrast) **and** the
  PBR shading / env-light integration (replacing nvdiffrec `renderutils`) — the texture *voxels*
  already come from an MIT model; only bake-to-UV and relight are tainted.

## Taint summary (see the audit for the full table + links)

- **Must replace (NC):** nvdiffrast, nvdiffrec/renderutils (both NVIDIA Source Code License),
  `briaai/RMBG-2.0` background remover (CC BY-NC 4.0).
- **Obligation, not blocker:** DINOv3 image conditioner — commercial-permitted, needs "Built with
  DINOv3" attribution + gated download; cannot be swapped (flow models trained on its features).
- **Clean (MIT/CC0):** TRELLIS.2-4B weights, CuMesh, FlexGEMM, utils3d, o-voxel, bundled HDRIs, and
  all stock deps.
- **GPL but isolated:** Blender `data_toolkit/blender_script/` (training-data prep, out-of-process) —
  keep out of anything shipped.

## Findings

- [2026-07-15 — TRELLIS v1 nvdiffrast import-graph trace](findings/2026-07-15-trellis-nvdiffrast-import-graph.md)
  — baseline: v1's geometry lane is nvdiffrast-free out of the box.
- [2026-07-15 — TRELLIS.2 & Hunyuan3D-2.1 trace](findings/2026-07-15-trellis2-hunyuan-nvdiffrast-trace.md)
  — v2 geometry import-requires nvdiffrast via eager `o_voxel.postprocess` (one-line patch);
  Hunyuan3D-2.1 is license-gated repo-wide (not applicable here).
- [2026-07-16 — TRELLIS.2 full taint audit](findings/2026-07-16-trellis2-taint-audit.md) — the
  complete license inventory driving WI 950.

Related: this line began inside the [rigged-avatars](../rigged-avatars/) track's nvdiffrast licensing
discussion before graduating here.
