"""ROCm guard for UnwrapMesh's fp64 batched solve (asset-harness WI 1761, from WI 1615).

On torch 2.10.0+rocm7.2.4 / gfx1151, hipBLAS's fp64 batched LU (`hipblasDgetrfBatched`) returns
HIPBLAS_STATUS_ALLOC_FAILED for mid-sized matrices beyond small batches (N=128 from 65,535 matrices,
N=224-384 above 16) with memory to spare. `UnwrapMesh` hits it in
`comfy_extras.mesh3d.uv_unwrap.parameterize.lscm_charts_batch`, whose GPU branch solves every
batchable chart at once, and the whole node fails.

A ComfyUI custom-node package that registers no nodes: at import it wraps `lscm_charts_batch` so
that when the GPU call raises that failure, the same call runs again on the function's own numpy
branch (`device=None`). Any other exception propagates. Active on HIP builds or when
ROCM_UNWRAP_GUARD=1; ROCM_UNWRAP_GUARD=0 switches it off. Install by copying this directory into
the checkout's `custom_nodes/`.
"""
import functools
import logging
import os

import torch

_ENV = "ROCM_UNWRAP_GUARD"
_MARKER = "HIPBLAS_STATUS_ALLOC_FAILED"
_log = logging.getLogger("rocm_unwrap_guard")

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

fallbacks = 0   # how many calls fell back to the CPU in this process


def wanted() -> bool:
    """Whether the guard should be active for this process."""
    flag = os.environ.get(_ENV)
    if flag == "0":
        return False
    if flag == "1":
        return True
    return bool(getattr(torch.version, "hip", None))


def is_alloc_failure(exc: BaseException) -> bool:
    """The one failure the guard handles: hipBLAS refusing to allocate for a batched solve."""
    return isinstance(exc, RuntimeError) and _MARKER in str(exc)


def guarded(original):
    """Wrap an `lscm_charts_batch`-shaped function: on the allocation failure, rerun with device=None."""
    @functools.wraps(original)
    def call(*args, **kwargs):
        global fallbacks
        try:
            return original(*args, **kwargs)
        except RuntimeError as exc:
            if not is_alloc_failure(exc) or kwargs.get("device") is None:
                raise
            fallbacks += 1
            if fallbacks == 1:
                _log.warning("rocm_unwrap_guard: GPU batched solve refused (%s); solving on the CPU", _MARKER)
            return original(*args, **{**kwargs, "device": None})
    call.rocm_unwrap_guard_original = original
    return call


def install(param_module=None) -> bool:
    """Wrap `param_module.lscm_charts_batch`; idempotent. Returns whether the guard is installed."""
    if param_module is None:
        from comfy_extras.mesh3d.uv_unwrap import parameterize as param_module  # noqa: PLC0415
    current = getattr(param_module, "lscm_charts_batch", None)
    if current is None:
        _log.warning("rocm_unwrap_guard: parameterize has no lscm_charts_batch; nothing installed")
        return False
    if getattr(current, "rocm_unwrap_guard_original", None) is not None:
        return True
    param_module.lscm_charts_batch = guarded(current)
    return True


if wanted():
    try:
        installed = install()
    except ImportError:
        installed = False   # imported outside ComfyUI (the unit test); install() is called explicitly there
        _log.info("rocm_unwrap_guard: comfy_extras not importable here; nothing installed")
    if installed:
        _log.info("rocm_unwrap_guard: active — UnwrapMesh's batched solve falls back to the CPU on %s", _MARKER)
else:
    _log.info("rocm_unwrap_guard: inactive (not a HIP build, or %s=0)", _ENV)
