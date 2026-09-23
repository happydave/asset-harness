# The TRELLIS.2 NaN is a ROCm GEMM defect for M > 2^20 rows with a small N

**WI 1613** · 2026-09-22 · ai2 (R9700, gfx1201, torch `2.10.0+rocm7.2.4`, HIP 7.2.53211) ·
follows [2026-09-19's WI 1600 findings](../../../../tickets/docs/pending/1600-ah-spike-trellis2-comfyui-core-rocm/spike.md)

## The finding

`torch.nn.functional.linear(x, w)` on this stack returns wrong, run-to-run non-deterministic
results when `x` has **more than 2^20 rows** and `w` has **16 or fewer output features**. Random
data, no model:

| M (rows) | N | wrong outputs (|dev| > 1 vs CPU fp32) |
|---|---|---|
| 1,048,576 | 8 | 0 |
| 1,048,577 | 8 | 8 |
| 1,577,827 | 8 | 4,171,838 (a third) |
| 1,577,827 | 16 | 8,338,470 |
| 1,577,827 | 64 / 128 | 0 / 0 |

K (64, 128, 256) does not matter; fp16, bf16 and fp32 are all affected (fp32 max deviation ~330).
The same call is correct and deterministic on an RTX 5070 and on the CPU.

The TRELLIS.2 shape decoder's per-voxel subdivision heads are `Linear(C, 8)` over every voxel of a
stage; above a million voxels (the 1024-and-up cascade; not the 512 decode) they hit this shape. At
fp16 the wrong values overflow to inf and become the NaN vertices WI 1600 saw; at fp32 the mesh is
finite and silently wrong (a different vertex count on every run). **Every ROCm decode of the test
latent was wrong, the NaN-free ones included.** The CUDA and CPU decodes agree with each other.

## The workaround

Apply every decoder `Linear` in chunks of at most 2^20 rows (`workaround_chunked_linear.py`):
the reference mesh comes back (6,481,922 vertices, 0 NaN, identical on four runs), and the decode
is faster (2 s against 5.5–9.7 s on the broken path). **Carried into the lane by WI 1741** as the
`prototypes/trellis2-comfyui/rocm_gemm_guard/` custom-node package (install into the mounted
checkout's `custom_nodes/`; active on HIP builds; `ROCM_GEMM_GUARD=0` off, `=1` forces on); its
live gate decodes a saved latent twice and requires the reference count. The upstream report is
WI 1743 (the owner files or approves the filing).

## Scripts

All in `prototypes/trellis2-comfyui/`: `run_trellis2_decode.py`, `trellis2_latent_io.py` +
`wi1613_latent_io/`, `bisect_decode.py`, `repro_linear.py`, `repro_synthetic.py`,
`workaround_chunked_linear.py`. Evidence and the full trail: the WI 1613 spike record in tickets.

## Caution for the rest of the estate's ROCm work

Any per-row head with a small output width over more than a million rows — sparse-voxel decoders,
point-cloud heads, per-token classifiers — is exposed on this toolchain until it is fixed.
