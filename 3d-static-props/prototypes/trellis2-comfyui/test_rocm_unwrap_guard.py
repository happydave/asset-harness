#!/usr/bin/env python3
"""Tests for the ROCm unwrap guard, CPU only, plain `python3 test_rocm_unwrap_guard.py`, no pytest.

The guard catches exactly one failure and reruns the same call on the function's own CPU branch.
Everything here drives fakes shaped like `lscm_charts_batch`; the fallback's output is by
construction the real function's `device=None` output.
"""
import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["ROCM_UNWRAP_GUARD"] = "1"
import rocm_unwrap_guard as G  # noqa: E402

FAILS = []
ALLOC = ("CUDA error: HIPBLAS_STATUS_ALLOC_FAILED when calling `hipblasDgetrfBatched( handle, n, "
         "dA_array, ldda, ipiv_array, info_array, batchsize)`")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


class Fake:
    """Records its calls; raises `exc` when given a device (or on every call with `always`), and
    otherwise returns a result tagged by device."""
    def __init__(self, exc=None, always=False):
        self.exc, self.always, self.calls = exc, always, []

    def __call__(self, *args, device=None):
        self.calls.append((args, device))
        if self.exc is not None and (device is not None or self.always):
            raise self.exc
        return {"device": device, "args": args}


def main():
    print("rocm_unwrap_guard")
    # A1 — the predicate
    check("the hipBLAS allocation failure is recognised", G.is_alloc_failure(RuntimeError(ALLOC)))
    check("another RuntimeError is not", not G.is_alloc_failure(RuntimeError("CUDA error: out of memory")))
    check("another exception type is not", not G.is_alloc_failure(ValueError("x")))
    check("the text in a non-RuntimeError is not", not G.is_alloc_failure(MemoryError(ALLOC)))

    gpu = types.SimpleNamespace(type="cuda")
    # A2 — fallback
    f = Fake(RuntimeError(ALLOC)); w = G.guarded(f); before = G.fallbacks
    try:
        out = w(1, 2, 3, device=gpu)
    except RuntimeError as e:
        out = f"raised: {e}"
    check("on the failure the result is the device=None call's", out == {"device": None, "args": (1, 2, 3)}, out)
    check("two calls: the device, then None, with the same arguments",
          [(a, d) for a, d in f.calls] == [((1, 2, 3), gpu), ((1, 2, 3), None)], f.calls)
    check("the fallback is counted", G.fallbacks == before + 1, G.fallbacks)
    # A3 — other failures propagate, no retry
    f = Fake(RuntimeError("CUDA error: out of memory")); w = G.guarded(f)
    try:
        w(1, device=gpu); check("another RuntimeError propagates", False, "no exception")
    except RuntimeError as e:
        check("another RuntimeError propagates", "out of memory" in str(e))
    check("no second call on another error", len(f.calls) == 1, f.calls)
    f = Fake(RuntimeError(ALLOC), always=True); w = G.guarded(f)
    try:
        w(1, device=None); check("the failure with device=None already propagates", False, "no exception")
    except RuntimeError:
        check("the failure with device=None already propagates", len(f.calls) == 1, f.calls)
    f = Fake(RuntimeError(ALLOC), always=True); w = G.guarded(f)
    try:
        w(1, device=gpu); check("a failing CPU fallback propagates", False, "no exception")
    except RuntimeError:
        check("a failing CPU fallback propagates, after exactly two calls", len(f.calls) == 2, f.calls)
    # A4 — success passes through
    f = Fake(); w = G.guarded(f)
    check("success: one call, its result", w(7, device=gpu) == {"device": gpu, "args": (7,)} and len(f.calls) == 1)
    # A5 — install and switches
    mod = types.SimpleNamespace(lscm_charts_batch=Fake())
    original = mod.lscm_charts_batch
    check("install replaces the attribute", G.install(mod) and mod.lscm_charts_batch is not original)
    wrapped = mod.lscm_charts_batch
    check("install is idempotent", G.install(mod) and mod.lscm_charts_batch is wrapped)
    check("the original is kept on the wrapper", wrapped.rocm_unwrap_guard_original is original)
    check("install without the function returns False", G.install(types.SimpleNamespace()) is False)
    os.environ["ROCM_UNWRAP_GUARD"] = "0"
    check("ROCM_UNWRAP_GUARD=0 is not wanted", G.wanted() is False)
    os.environ["ROCM_UNWRAP_GUARD"] = "1"
    check("ROCM_UNWRAP_GUARD=1 is wanted", G.wanted() is True)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
