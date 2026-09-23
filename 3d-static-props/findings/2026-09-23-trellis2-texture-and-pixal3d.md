# Findings: the TRELLIS.2 texture tail and the Pixal3D arm on gfx1151

**Date:** 2026-09-23 · **Work item:** WI 1615 (tickets) · **Host:** `gtr`, Radeon 8060S (gfx1151),
ComfyUI v0.34.6, image `localhost/wi1600-comfyui:0.34.6`

## Verdicts

- **The shipped template's texture tail does not run on gfx1151 unguarded.** Both arms fail at
  `UnwrapMesh`. With WI 1761's guard it runs (update below).
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

## Update 2026-09-23 (WI 1761): the texture tail runs with a guard

`rocm_unwrap_guard` (a custom node) reruns the refused fp64 batched solve on the parameterization's
own CPU branch. With it, both arms finish on `gtr`. The fallback fired once in each run.

| Arm | Time | Triangles | Textures | Peak GTT from an empty pool |
|---|---|---|---|---|
| TRELLIS.2 | 1,890 s | 699,494 | base colour, metallic-roughness, occlusion (4096) | 61.3 GB |
| Pixal3D (default) | 1,090 s | 698,297 | same | 40.3 GB |

- Both renders show the crate's orange trim, rust, latches, handle and rivets, with no untextured
  patches.
- The Pixal3D asset keeps the camera pose it estimated from the input, so it sits tilted in its
  frame; TRELLIS.2's is axis-aligned.
- Neither reproduces the input's small orange label on the front face.
- With the guard active, `RemeshMesh` peaked about 35 GB higher than without it in 4 of 4 runs.
  The mechanism is not found (WI 1766). *Corrected by the WI 1766 update below: the peak was
  `UnwrapMesh`'s atlas packer, not `RemeshMesh`.*

## The comparison for WI 1602

`samples-2026-09-23/crate_trellis2_vs_moge.png`: the input; TRELLIS.2 and Pixal3D textured (WI
1761); MoGe's relief from its own camera; and MoGe's cleaned 22k mesh from the same orbit camera. TripoSR never produced a crate (2026-06-22: blocked at model load), so MoGe is the
prior lane's only output. The MoGe mesh is a one-camera relief: from any orbit angle it is shards.

## Tools

In `prototypes/trellis2-comfyui/`:
- `template_to_api.py`: UI template to API graph via `/object_info`. It stops on anything it would
  otherwise guess.
- `run_api_graph.py`: queue a graph and wait; the exit code says success, error, refusal or timeout.
- `side_by_side.py`: a labelled row of renders.

## Update 2026-09-23 (WI 1766): the extra memory was the atlas packer, and numba removes it

- **Where it went.** Guarded runs peaked about 35 GB higher than unguarded ones. That was not
  `RemeshMesh`: a per-stage probe put it in `UnwrapMesh`'s atlas packer (`pack_bitmap_concat`). The
  packer demanded 28.4 GiB, and torch kept it reserved until the next model load. Unguarded runs
  never reach the packer, because they fail at the solve before it. The first reading came from a
  progress bar's flush timestamp.
- **Why.** ComfyUI's packer uses numba when it imports, and otherwise a torch path on the GPU that
  pads every chart's tensors to the largest chart. The lane image had no numba. On one captured input,
  three replays without numba each demanded 29,104 MiB in the packer; three with numba demanded 0.
  Both gave the same 3,734 charts and valid UVs; numba's atlas is about 3% larger in area.
- **The fix.** The image carries hash-pinned numba 0.67.0 and llvmlite 0.49.0, installed without
  dependencies; the freeze diff is exactly those two. Upstream reworked the same padded tensors in
  v0.35.0 (`0eb098b5`).

| Run on the rebuilt image | Pool | Peak GTT | Lowest available | Result |
|---|---|---|---|---|
| TRELLIS.2 arm | empty | 25,944 MiB | 80.4 GiB | textured, 1,920 s |
| Pixal3D arm | empty | 22,773 MiB | 81.7 GiB | textured, 1,090 s |
| TRELLIS.2 arm, beside a 50,540 MiB stand-in | 50.7 GB held | 76,064 MiB | 32.6 GiB | textured, 1,861 s; watchdog silent |

One run each, descriptive. The raw decode still varies between runs (14.86M and 12.88M vertices
here), and the packer's old demand varied with it.

