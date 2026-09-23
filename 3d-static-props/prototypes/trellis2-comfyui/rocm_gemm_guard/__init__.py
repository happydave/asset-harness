"""ROCm GEMM guard for the TRELLIS.2 shape decoder (asset-harness WI 1741, from WI 1613).

On torch 2.10.0+rocm7.2.4 / gfx1201 a matmul of more than 2^20 rows against a weight with a small
output width returns wrong, non-deterministic results; the decoder's per-voxel heads
(`SparseLinear(C, 8)`, `SparseLinear(C, 7)`) hit that shape above a million voxels and the mesh
comes out wrong — NaN at fp16, silently different at fp32. Exactly 2^20 rows is correct, so a
`Linear` applied in 2^20-row chunks is.

A ComfyUI custom-node package that registers no nodes: at import it replaces
`comfy.ldm.trellis2.vae.SparseLinear` with a factory whose modules apply their forward in row
chunks. Active on HIP builds (`torch.version.hip`) or when ROCM_GEMM_GUARD=1; ROCM_GEMM_GUARD=0
switches it off. Install by copying this directory into the checkout's `custom_nodes/`.
"""
import logging
import os

import torch

CHUNK = 1 << 20
_ENV = "ROCM_GEMM_GUARD"
_log = logging.getLogger("rocm_gemm_guard")

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def wanted() -> bool:
    """Whether the guard should be active for this process."""
    flag = os.environ.get(_ENV)
    if flag == "0":
        return False
    if flag == "1":
        return True
    return bool(getattr(torch.version, "hip", None))


def chunked_forward(module, orig_forward, chunk=CHUNK):
    """A forward for a SparseLinear-built module that never hands more than `chunk` rows to one GEMM.

    The module's input is a sparse tensor (`.feats`, `.replace`) or a plain tensor; the original
    forward is what runs on each slice, so the arithmetic is the module's own.
    """
    def forward(inp):
        feats = inp.feats if hasattr(inp, "feats") else inp
        if feats.shape[0] <= chunk:
            return orig_forward(inp)
        parts = []
        for s in range(0, feats.shape[0], chunk):
            piece = inp.replace(feats[s:s + chunk]) if hasattr(inp, "feats") else feats[s:s + chunk]
            out = orig_forward(piece)
            parts.append(out.feats if hasattr(out, "feats") else out)
        joined = torch.cat(parts, dim=0)
        return inp.replace(joined) if hasattr(inp, "feats") else joined
    return forward


def guard_factory(original):
    """Wrap a SparseLinear-style factory so every module it builds forwards in chunks."""
    def factory(*args, **kwargs):
        module = original(*args, **kwargs)
        module.forward = chunked_forward(module, module.forward)
        module.rocm_gemm_guard = CHUNK
        return module
    factory.rocm_gemm_guard_original = original
    return factory


def install(vae_module=None) -> bool:
    """Replace `vae_module.SparseLinear`; idempotent. Returns whether the guard is installed."""
    if vae_module is None:
        import comfy.ldm.trellis2.vae as vae_module  # noqa: PLC0415
    current = getattr(vae_module, "SparseLinear", None)
    if current is None:
        _log.warning("rocm_gemm_guard: comfy.ldm.trellis2.vae has no SparseLinear; nothing installed")
        return False
    if getattr(current, "rocm_gemm_guard_original", None) is not None:
        return True
    vae_module.SparseLinear = guard_factory(current)
    return True


if wanted():
    try:
        installed = install()
    except ImportError:
        installed = False   # imported outside ComfyUI (the unit test); install() is called explicitly there
        _log.info("rocm_gemm_guard: comfy not importable here; nothing installed")
    if installed:
        _log.info("rocm_gemm_guard: active — TRELLIS.2 SparseLinear layers run in %d-row chunks", CHUNK)
else:
    _log.info("rocm_gemm_guard: inactive (not a HIP build, or %s=0)", _ENV)
