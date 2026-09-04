# Track: trellis2-clean

**Status:** 🟡 **Active — fork created, audit done, hardware spike open** (2026-08-27). Goal: make
Microsoft's **TRELLIS.2** (4B image→3D; MIT weights + code) usable for **commercial** game-asset
generation by removing its non-commercial NVIDIA dependencies. Fork:
`github.com/happydave/TRELLIS.2`. Tracked as **WI 950**.

**Checkout:** `/home/dave/Documents/projects/TRELLIS.2` (cloned 2026-08-27; needs `--recursive` for the
Eigen submodule). `main` @ `75fbf01` is **byte-identical to upstream** — no patch work has started. The
fork had not been cloned locally before, presumed lost in the July drive swap; this directory
(`trellis2-clean/`) is a **docs track only**, not the code.

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

## Hardware / substrate

**TRELLIS.2 is not CUDA-only** — this corrects the track's original conclusion (see the 2026-08-27
correction appended to the v2 trace). All three MIT extensions (o-voxel, CuMesh, FlexGEMM) carry
`BUILD_TARGET=rocm` paths, FlexGEMM's compute is Triton, and `setup.sh` **refuses nvdiffrast and
nvdiffrec on HIP** — so on AMD the clean geometry lane is the default *by construction*. The ROCm lane
and the clean-licence lane turn out to be the same lane.

The binding constraint is VRAM, not vendor: the README demands **≥24 GiB**.

| Host | GPU | VRAM | Toolchain | Verdict |
|---|---|---|---|---|
| workstation | RTX 5070 (sm_120) | 12 GiB | CUDA 12.4 — predates sm_120 | 12 GiB short, toolchain behind its own arch |
| `ai2` | R9700 (gfx1201) | 31.9 GiB | ROCm 7.2.4 — ahead of gfx1201's 6.4+ | **preferred target** |

Runs in a rootless-podman ROCm container on `ai2`, inheriting the recipe and bare-metal-parity verdict
from [gen-workers WI 1064](../../../tickets/docs/pending/1064-genworkers-rocm-container-perf-spike/spike.md).
Base image `rocm/pytorch:rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.10.0` supplies a version-matched
torch + hipcc + ROCm-Triton, so `setup.sh --new-env` is skipped entirely. Note the card is shared and
foundry-arbitrated — see the [gen-workers design](../../../tickets/docs/projects/gen-workers/design.md).

Open question: hipify is unproven for **o-voxel and CuMesh** (only FlexGEMM shows a hand-written AMD
shim). [WI 1197](../../../tickets/docs/pending/1197-trellis2-rocm-geometry-spike/spike.md) settles it.

## Findings

- [2026-07-15 — TRELLIS v1 nvdiffrast import-graph trace](findings/2026-07-15-trellis-nvdiffrast-import-graph.md)
  — baseline: v1's geometry lane is nvdiffrast-free out of the box.
- [2026-07-15 — TRELLIS.2 & Hunyuan3D-2.1 trace](findings/2026-07-15-trellis2-hunyuan-nvdiffrast-trace.md)
  — v2 geometry import-requires nvdiffrast via eager `o_voxel.postprocess` (one-line patch);
  Hunyuan3D-2.1 is license-gated repo-wide (not applicable here). **Carries a 2026-08-27 correction:
  its CUDA-only portability conclusion was wrong.**
- [2026-07-16 — TRELLIS.2 full taint audit](findings/2026-07-16-trellis2-taint-audit.md) — the
  complete license inventory driving WI 950.

Related: this line began inside the [rigged-avatars](../rigged-avatars/) track's nvdiffrast licensing
discussion before graduating here.
