# TRELLIS.2 & Hunyuan3D-2.1 — same nvdiffrast/restricted-dep trace

**Date:** 2026-07-15
**Question:** Repeat the [TRELLIS v1 import-graph trace](2026-07-15-trellis-nvdiffrast-import-graph.md)
on **TRELLIS.2** and **Hunyuan3D-2.1**: does a shape-only (geometry) lane avoid the restricted
NVIDIA tooling (nvdiffrast = NVIDIA Source Code License, non-commercial)?
**Method:** shallow-cloned each repo, traced imports statically. No execution.

## TRELLIS.2 — `github.com/microsoft/TRELLIS.2` (4B, MIT license)

**Verdict: geometry is nvdiffrast-*clean in computation* but nvdiffrast-*required at import*, unlike
v1. A clean shape-only lane needs a one-line patch.**

- Top-level LICENSE = **MIT** (same as v1). nvdiffrast appears in `trellis2/renderers/mesh_renderer.py`,
  `trellis2/renderers/pbr_mesh_renderer.py` (both **lazy** — imported inside functions, guarded by
  `if 'dr' not in globals()`), `trellis2/pipelines/trellis2_texturing.py` (the **texturing/paint**
  pipeline, module-level), and **`o-voxel/o_voxel/postprocess.py`** (module-level; defines `to_glb` —
  the export/bake).
- The image-to-3D pipeline (`trellis2_image_to_3d.py`) cleanly **separates** `decode_shape_slat` (→
  `List[Mesh]`, geometry) from `decode_tex_slat` (texture voxels). The `Mesh` representation
  (`representations/mesh.py`) imports no nvdiffrast, so exporting raw verts/faces (trimesh) is clean.
- **The catch (differs from v1):** the geometry decoder `trellis2/models/sc_vaes/fdg_vae.py` does
  `from o_voxel.convert import flexible_dual_grid_to_mesh` at module level, and **`o_voxel/__init__.py`
  eagerly imports `postprocess`**:
  ```python
  from . import (convert, io, postprocess, rasterize, serialize)   # postprocess → import nvdiffrast
  ```
  So importing the geometry decoder transitively **import-requires nvdiffrast to be installed**, even
  though the mesh is actually built by o_voxel's `_C` CUDA extension (`flexible_dual_grid_to_mesh`),
  which does not call nvdiffrast. Of the eager-imported submodules, **only `postprocess` pulls
  nvdiffrast** (`rasterize`/`serialize`/`io`/`convert` do not).
- **Clean-lane recipe for v2:** a **one-line patch** to `o_voxel/__init__.py` (drop `postprocess`
  from the eager import, or make it lazy) makes the geometry import chain genuinely nvdiffrast-free;
  then run `decode_shape_slat` and export the `Mesh` yourself, never touching the texturing pipeline
  or renderers. Small, real fork — v1 needed no patch at all.
- **Portability:** o-voxel builds a custom CUDA extension (`setup.py` → `CUDAExtension`/nvcc, Eigen
  third-party; there is an `IS_HIP_EXTENSION` branch hinting at possible ROCm, unverified). So the
  geometry stage is still NVIDIA/CUDA-bound in practice — same "run on the RTX 5070" conclusion.

## Hunyuan3D-2.1 — `github.com/Tencent-Hunyuan/Hunyuan3D-2.1` (Tencent Community License)

**Verdict: no nvdiffrast anywhere — but the shape/texture split does NOT clean the license, because
the whole repo (geometry included) is under the Tencent Hunyuan 3D 2.1 Community License.**

- **Zero `nvdiffrast` imports** in the repo. Prior discover.md claim that "Hunyuan3D depends on
  nvdiffrast" is **wrong for 2.1** — the paint side uses Tencent's own bundled **`custom_rasterizer`**
  (`hy3dpaint/custom_rasterizer/`, a CUDA kernel `custom_rasterizer_kernel`) and
  `hy3dpaint/DifferentiableRenderer/MeshRender.py`. No kaolin either.
- The **shape** side (`hy3dshape/`) has **no rasterizer imports** — geometry is rasterizer-free (still
  CUDA/torch for the diffusion, but no custom rasterizer extension).
- **License is repo-wide and is the real gate.** Top-level LICENSE = **TENCENT HUNYUAN 3D 2.1
  COMMUNITY LICENSE AGREEMENT** — the same territorial (EU/UK/South Korea excluded, extends to
  Outputs) + 1M-MAU-gate license quoted verbatim in the [UltraShape finding](../../../../tickets/docs/projects/asset-studio/research/web-research-ultrashape.md).
  It blankets **both** shape and texture, so generating *geometry only* does not escape it — unlike
  TRELLIS, where the license is MIT and only the optional nvdiffrast paint stage is restricted.
  (Inconsistency worth flagging, consistent with the known Hunyuan pattern: `custom_rasterizer/setup.py`'s
  header line says "TENCENT HUNYUAN **NON-COMMERCIAL** LICENSE AGREEMENT" while the governing top-level
  file is the **Community** license — same LICENSE-vs-file drift the discover doc already noted for 2.0.)

## Net comparison (geometry/shape-only lane)

| Repo | License (geometry) | nvdiffrast on geometry path | Clean shape-only lane? |
|---|---|---|---|
| TRELLIS v1 | MIT | No (lazy renderers, clean decoder) | **Yes, out of the box** — verified |
| TRELLIS.2 (4B) | MIT | Import-required via eager `o_voxel.postprocess`, but never *called* | **Yes, after a 1-line `o_voxel/__init__.py` patch** |
| Hunyuan3D-2.1 | Tencent Community (territorial, MAU gate) | No nvdiffrast at all (uses `custom_rasterizer`) | **N/A — license gates geometry too**, split doesn't help |

**Takeaway:** the "generate geometry, texture in our own clean lane" escape hatch works for **both
TRELLIS versions** (v2 needs a trivial patch) because their license is MIT and nvdiffrast is confined
to texturing/export. It does **not** help **Hunyuan3D-2.1**, whose Community License restricts the
geometry itself — for Hunyuan the gate is the license, not a swappable sub-dependency. This is the
same license Hunyuan-derivative UltraShape 1.0 inherits (WI 937).

## Scope / not verified

- Static import traces only; not executed. TRELLIS.2 clones probed at default HEAD 2026-07-15.
- Whether merely *importing* (not calling) nvdiffrast creates any NC-license obligation is a legal
  question, not a code one; the patch removes the question entirely for v2. Not legal advice.
- o-voxel `IS_HIP_EXTENSION` (ROCm) branch not tested — portability to AMD remains unverified for v2.
