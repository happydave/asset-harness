#!/usr/bin/env python3
"""Tests for the ROCm GEMM guard, CPU only, plain `python3 test_rocm_gemm_guard.py`, no pytest.

The guard's job is row batching and nothing else: chunked output must equal the unchunked output
to float rounding (a remainder chunk takes a different BLAS kernel), chunk boundaries must fall on multiples of 2^20, and a small input must not be chunked.
The forward is exercised through a fake sparse tensor with the `.feats`/`.replace` shape the
decoder's tensors have, and through a plain tensor.
"""
import os
import sys
import types
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["ROCM_GEMM_GUARD"] = "1"          # force active on this CPU host
import rocm_gemm_guard as G  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


class Sparse:
    """The two members the guard relies on, as comfy.ldm.trellis2.vae's SparseTensor has them."""
    def __init__(self, feats):
        self.feats = feats

    def replace(self, feats):
        return Sparse(feats)


def make_linear(calls):
    """A deterministic fp32 Linear whose forward records the row count of every call."""
    torch.manual_seed(1)
    lin = torch.nn.Linear(16, 8)

    def forward(inp):
        feats = inp.feats if hasattr(inp, "feats") else inp
        calls.append(feats.shape[0])
        out = torch.nn.functional.linear(feats, lin.weight, lin.bias)
        return inp.replace(out) if hasattr(inp, "feats") else out
    lin.forward = forward
    return lin


def main():
    print("rocm_gemm_guard")
    check("guard reports wanted() under ROCM_GEMM_GUARD=1", G.wanted() is True)

    # install() against a fake vae module
    calls = []
    fake_vae = types.SimpleNamespace(SparseLinear=lambda *a, **k: make_linear(calls))
    check("install replaces SparseLinear", G.install(fake_vae) and fake_vae.SparseLinear is not None)
    factory = fake_vae.SparseLinear
    check("install is idempotent", G.install(fake_vae) and fake_vae.SparseLinear is factory)

    for rows in ((1 << 20) - 1, 1 << 20, (1 << 20) + 1, 3 * (1 << 20) + 7):
        calls.clear()
        module = factory()
        x = torch.randn(rows, 16)
        ref = torch.nn.functional.linear(x, module.weight, module.bias)
        out = module.forward(Sparse(x))
        # A tolerance, not bitwise: a one-row remainder takes a different CPU BLAS kernel than the
        # big GEMM and rounds differently in the last bit; the guard changes batching, not values.
        dev = (out.feats - ref).abs().max().item()
        check(f"{rows} rows (sparse): chunked == unchunked within 1e-5", dev <= 1e-5, f"max|dev|={dev}")
        expected_calls = [min(1 << 20, rows - s) for s in range(0, rows, 1 << 20)]
        check(f"{rows} rows: GEMM row counts {expected_calls[:2]}…", calls == expected_calls, calls[:4])
        check(f"{rows} rows: no call above 2^20", max(calls) <= (1 << 20), max(calls))
        calls.clear()
        out2 = module.forward(x)
        dev2 = (out2 - ref).abs().max().item()
        check(f"{rows} rows (plain tensor): chunked == unchunked within 1e-5", dev2 <= 1e-5, f"max|dev|={dev2}")

    # off switch: the original forward is called once with everything
    os.environ["ROCM_GEMM_GUARD"] = "0"
    check("guard reports not wanted() under ROCM_GEMM_GUARD=0", G.wanted() is False)
    calls.clear()
    plain = make_linear(calls)
    x = torch.randn((1 << 20) + 5, 16)
    plain.forward(Sparse(x))
    check("unguarded module makes one call with all rows", calls == [(1 << 20) + 5], calls)

    # a vae module without SparseLinear: nothing installed, no exception
    check("install on a module without SparseLinear returns False", G.install(types.SimpleNamespace()) is False)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
