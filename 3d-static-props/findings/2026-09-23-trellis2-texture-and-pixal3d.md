# Findings: the TRELLIS.2 texture tail and the Pixal3D arm on gfx1151

**Date:** 2026-09-23 · **Work item:** WI 1615 (tickets) · **Host:** `gtr`, Radeon 8060S (gfx1151),
ComfyUI v0.34.6, image `localhost/wi1600-comfyui:0.34.6`

## Verdicts

- **The shipped template's texture tail does not run on gfx1151.** Both arms fail at `UnwrapMesh`.
  - The error is `HIPBLAS_STATUS_ALLOC_FAILED` in `hipblasDgetrfBatched`: the fp64 batched solve
    in the UV parameterization (`comfy_extras/mesh3d/uv_unwrap/parameterize.py`,
    `lscm_charts_batch`), which always runs on the compute device.
  - It is not memory: at least 26 GiB stayed available.
  - Reproduced alone, fp64 batched LU fails for mid-sized matrices beyond small batches. N=64 fails
    from 131,072 matrices, N=128 from 65,535, and N=224–384 above 16. N=512 passes at every batch
    tried. N=160–512 all pass at batch 16, and N ≤ 128 passed at 1,024.
  - `segmenter=adaptive` does not avoid it. A guard in the `rocm_gemm_guard` pattern is WI 1761.
  - Everything after the unwrap (the voxel bake, the normal and AO bakes, `ApplyTextureToMesh`)
    remains unrun here.
- **The template's default arm is Pixal3D, not TRELLIS.2.** Its `PrimitiveBoolean` "Switch to
  Trellis2" is false.
  - Pixal3D (single image, MoGe camera estimate) runs up to the same unwrap: raw decode about
    9M vertices, 760–1,140 s to the failure.
  - **Its raw decode is not repeatable.** Two runs with identical settings gave 8,933,506 and
    9,356,046 vertices. TRELLIS.2 gave 12,875,726 on both of its runs. Recorded, not investigated.
    *2026-09-23, WI 1761:* TRELLIS.2's raw decode varies across runs too: 12,875,726 in four runs
    and 14,860,255 in two, guard on and off. A count taken at this stage is not a gate on either
    arm.
- **No multi-view path exists at v0.34.6.** `Pixal3DMultiViewConditioning` first appears in
  v0.36.0. The multi-view weights are published in Comfy-Org/Pixal3D. Upgrading is WI 1751.
- **The template's texture resolution is 4096.** A `PrimitiveInt` feeds both
  `UnwrapMesh.resolution` and `BakeTextureFromVoxel.texture_size`, overriding the bake's 2048 widget.

## The comparison for WI 1602

`samples-2026-09-23/crate_trellis2_vs_moge.png`: the input, TRELLIS.2's decimated geometry (WI
1745, untextured), MoGe's relief from its own camera, and MoGe's cleaned 22k mesh from the same
orbit camera. TripoSR never produced a crate (2026-06-22: blocked at model load), so MoGe is the
prior lane's only output. The MoGe mesh is a one-camera relief: from any orbit angle it is shards.

## Tools

In `prototypes/trellis2-comfyui/`:
- `template_to_api.py`: UI template to API graph via `/object_info`. It stops on anything it would
  otherwise guess.
- `run_api_graph.py`: queue a graph and wait; the exit code says success, error, refusal or timeout.
- `side_by_side.py`: a labelled row of renders.
