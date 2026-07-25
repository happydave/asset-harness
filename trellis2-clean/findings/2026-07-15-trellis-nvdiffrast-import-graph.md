# TRELLIS shape-stage import graph — does the geometry lane avoid nvdiffrast?

**Date:** 2026-07-15
**Question (from `discover.md` Open Questions):** Does the shape-only stage of TRELLIS truly avoid
`nvdiffrast` (NVIDIA Source Code License = non-commercial research/eval only), so we can run TRELLIS
for **geometry** and texture in our own clean lane without inheriting the NC license?
**Method:** shallow-cloned `github.com/microsoft/TRELLIS` (v1) and its pinned FlexiCubes submodule,
traced the import graph statically. No execution.
**Verdict:** **CONFIRMED for TRELLIS v1 — the geometry lane is nvdiffrast-free and NC-license-free.**

## Evidence

### 1. Only two files import nvdiffrast, both on the texture/export path
```
trellis/renderers/mesh_renderer.py:2      import nvdiffrast.torch as dr
trellis/utils/postprocessing_utils.py:5   import nvdiffrast.torch as dr
```
- `postprocessing_utils.py` (has `to_glb`, `bake_texture`, `parametrize_mesh`/xatlas) is imported
  **only** by the top-level demo/app scripts (`example.py`, `example_text.py`, `example_variant.py`,
  `app.py`, `app_text.py`) — i.e. the **texture-bake → glb export** step, invoked explicitly as
  `postprocessing_utils.to_glb(gs, mesh, …)`.
- `mesh_renderer.py` (`MeshRenderer`) is imported by `render_utils.py` (`render_multiview`, used by
  `to_glb`'s texture baking) and by the mesh-decoder **trainer**. Its `import nvdiffrast` is
  **unguarded** (module top-level).

### 2. The pipeline and geometry decoder import no nvdiffrast
- `trellis/pipelines/trellis_image_to_3d.py` imports: torch/torchvision/PIL/rembg + `base`,
  `samplers`, `modules.sparse`. No renderers, no postprocessing, no nvdiffrast.
- `trellis/representations/mesh/cube2mesh.py` (`SparseFeatures2Mesh` → `MeshExtractResult`, the
  geometry) imports: torch, `SparseTensor`, easydict, `utils_cube`, `FlexiCubes`. No nvdiffrast.
- `trellis/renderers/__init__.py` is **lazy** (`__getattr__` + `importlib`), so `import trellis`
  and accessing the pipeline never trigger `mesh_renderer` (and thus never require nvdiffrast).

**⇒ Flow:** `pipeline.run(image)` yields a `mesh` `MeshExtractResult` (verts + faces) with zero
nvdiffrast. Exporting those raw verts/faces yourself (e.g. trimesh) stays nvdiffrast-free. Only
`to_glb` (TRELLIS's own texture bake) pulls nvdiffrast — which we deliberately skip in favour of
"texture in Blender / our clean lane."

### 3. Residual NVIDIA touch-point in the geometry decoder is license-clean
FlexiCubes is a **vendored fork**: submodule `MaxtirError/FlexiCubes`, pinned commit
`815e075a2a400d06c48d94c347674344ed6ae5c5` (== the fork's default HEAD I inspected), **LICENSE =
Apache-2.0**. Its `flexicubes.py` has exactly one non-torch import:
```
from kaolin.utils.testing import check_tensor
```
used only inside `assert … check_tensor(x, shape, throw=False)` shape validations. **kaolin is
Apache-2.0** (verified against `NVIDIAGameWorks/kaolin` LICENSE) — permissive, **not** the restricted
NVIDIA Source Code License. So this is a *portability* dependency (kaolin ships CUDA-only ops →
keeps TRELLIS geometry on an NVIDIA GPU, matching the prior "run on the RTX 5070" conclusion), **not**
a license taint, and it is a one-line stub if we ever want it gone.

## Implications

- The **"generate geometry with TRELLIS, texture ourselves"** escape hatch is real and verified for
  v1. It cleanly avoids the only NC-licensed component (nvdiffrast). We do **not** need to build our
  own replacement for nvdiffrast to get a license-clean TRELLIS geometry lane — we simply never call
  the texture-bake/`to_glb` path. (A replacement would only matter if we wanted TRELLIS's *own*
  textured output to be commercially clean, which the plan does not.)
- **Clean-lane guardrail:** import only the pipeline + geometry; do **not** import
  `render_utils`/`postprocessing_utils` or touch `MeshRenderer` (all unguarded-import nvdiffrast).
- **Portability is unchanged:** kaolin/FlexiCubes keep the geometry stage on NVIDIA (CUDA) — the AMD
  hostility and "RTX 5070 or nowhere" conclusion stand; only the *license* worry is cleared.

## Scope / not verified

- **TRELLIS v1 only.** TRELLIS.2 (Dec 2025, 4B) is a separate codebase — repeat this trace before
  relying on its shape-only stage. Same for Hunyuan3D's shape stage.
- Static import trace only; not executed. A dynamic import (e.g. inside a rarely-hit branch) would
  not be caught by grep, though the lazy/eager structure above makes that unlikely on the geometry
  path.
