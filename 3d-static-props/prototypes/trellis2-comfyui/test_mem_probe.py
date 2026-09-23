#!/usr/bin/env python3
"""Tests for the memory probe, CPU only, plain `python3 test_mem_probe.py`, no pytest.

The probe wraps named stage functions and records memory counters around each call. These tests
drive it with fake modules, a fake counter source and a fake GTT reader; nothing touches a GPU.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.pop("MEM_PROBE_DIR", None)
import mem_probe as P  # noqa: E402
import torch  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


class FakeCounters:
    """Allocator counters a test moves by hand; peaks track the highest value since the last reset."""
    def __init__(self):
        self.a = self.r = self.pa = self.pr = 0

    def set(self, a, r):
        self.a, self.r = a, r
        self.pa, self.pr = max(self.pa, a), max(self.pr, r)

    def allocated(self):
        return self.a

    def reserved(self):
        return self.r

    def peaks(self):
        return self.pa, self.pr

    def reset_peaks(self):
        self.pa, self.pr = self.a, self.r


def fake_modules():
    npp = types.SimpleNamespace(remesh_narrow_band_dc=lambda *a, **k: "remeshed",
                                qem_decimate_simplify=lambda *a, **k: "decimated",
                                _uv_unwrap=lambda *a, **k: ("vmap", "idx", "uvs"))
    par = types.SimpleNamespace(lscm_charts_batch=lambda *a, **k: {"solved": True})
    pack = types.SimpleNamespace(pack_bitmap_concat=lambda *a, **k: "packed",
                                 apply_placements_concat=lambda *a, **k: "applied",
                                 _HAVE_NUMBA_PACK=False)
    return {"comfy_extras.nodes_mesh_postprocess": npp,
            "comfy_extras.mesh3d.uv_unwrap.parameterize": par,
            "comfy_extras.mesh3d.uv_unwrap.pack": pack}


def records(directory):
    with open(os.path.join(directory, "stages.jsonl")) as f:
        return [json.loads(line) for line in f]


def main():
    print("mem_probe")

    # results and exceptions pass through unchanged
    got = []
    probe = P.Probe(got.append, FakeCounters(), lambda: 7)
    sentinel = object()
    check("a wrapped stage returns the original's value", probe.wrap("s", lambda: sentinel)() is sentinel)
    boom = ValueError("boom")

    def raiser():
        raise boom
    try:
        probe.wrap("s", raiser)()
        raised = None
    except ValueError as exc:
        raised = exc
    check("a wrapped stage re-raises the original's exception object", raised is boom, repr(raised))
    check("the failing call is recorded as an error", got and got[-1]["ok"] is False and "boom" in got[-1]["error"], got[-1:])

    def hook_fails(args, kwargs):
        raise OSError("disk full")
    try:
        got_back = probe.wrap("s", lambda: sentinel, hook_fails)()
    except OSError as exc:
        got_back = exc
    check("a failing capture hook does not change the result", got_back is sentinel, repr(got_back))

    def sink_fails(record):
        raise OSError("disk full")
    try:
        got_back = P.Probe(sink_fails, FakeCounters()).wrap("s", lambda: sentinel)()
    except OSError as exc:
        got_back = exc
    check("a failing record sink does not change the result", got_back is sentinel, repr(got_back))

    # the record's fields, from counters moved inside the call
    c = FakeCounters(); c.set(100, 1000); got = []
    probe = P.Probe(got.append, c, lambda: 42)

    def grows():
        c.set(900, 5000)   # the stage's high point
        c.set(150, 5000)   # freed back into the cache
        return 1
    probe.wrap("grow", grows)()
    r = got[-1]
    fields = {"stage", "pid", "t_enter", "t_exit", "alloc_enter", "res_enter", "alloc_exit", "res_exit",
              "peak_alloc", "peak_res", "demand", "cache_growth", "gtt_enter", "gtt_exit", "ok", "error"}
    check("the record carries every field", fields <= set(r), sorted(fields - set(r)))
    check("demand is peak allocated over entry", r["demand"] == 800, r)
    check("cache growth is peak reserved over entry", r["cache_growth"] == 4000, r)
    check("exit counters are the values at exit", (r["alloc_exit"], r["res_exit"]) == (150, 5000), r)
    check("GTT is read at entry and exit", (r["gtt_enter"], r["gtt_exit"]) == (42, 42), r)

    # nesting: the outer stage's peak covers the inner stage's, across the inner's resets
    c = FakeCounters(); c.set(0, 0); got = []
    probe = P.Probe(got.append, c)

    def inner():
        c.set(700, 800)
        c.set(10, 800)
    w_inner = probe.wrap("inner", inner)

    def outer():
        c.set(50, 100)
        w_inner()
        c.set(60, 800)
    probe.wrap("outer", outer)()
    by = {x["stage"]: x for x in got}
    check("the inner stage's demand is its own", by["inner"]["demand"] == 650, by["inner"])
    check("the outer stage's peak is at least the inner's", by["outer"]["peak_alloc"] >= by["inner"]["peak_alloc"], by)
    check("the outer stage's demand includes the inner's high point", by["outer"]["demand"] == 700, by["outer"])

    # install
    with tempfile.TemporaryDirectory() as d:
        mods = fake_modules()
        h = P.install(mods, d, capture=False, counters=FakeCounters(), gtt_reader=lambda: 1)
        check("every present target is wrapped", sorted(h["wrapped"]) == sorted(t[0] for t in P.TARGETS), h)
        check("the packer's numba flag is reported", h["numba_pack"] is False, h)
        npp = mods["comfy_extras.nodes_mesh_postprocess"]
        check("a wrapped target still returns its value", npp._uv_unwrap(1) == ("vmap", "idx", "uvs"))
        h2 = P.install(mods, d, capture=False, counters=FakeCounters(), gtt_reader=lambda: 1)
        check("install is idempotent", h2["wrapped"] == [] and len(h2["already"]) == len(P.TARGETS), h2)
        check("the wrap is one layer deep", not hasattr(npp._uv_unwrap.mem_probe_original, "mem_probe_original"))
        check("the header is recorded", any(x.get("header") for x in records(d)))
    with tempfile.TemporaryDirectory() as d:
        mods = fake_modules()
        del mods["comfy_extras.mesh3d.uv_unwrap.pack"]
        del mods["comfy_extras.mesh3d.uv_unwrap.parameterize"].lscm_charts_batch
        h = P.install(mods, d, capture=False, counters=FakeCounters(), gtt_reader=lambda: 1)
        check("a missing module is named", any(m.startswith("pack:") for m in h["missing"])
              and any(m.startswith("apply:") for m in h["missing"]), h["missing"])
        check("a missing attribute is named", any(m.startswith("lscm_batch:") for m in h["missing"]), h["missing"])
        check("the present targets are still wrapped", set(h["wrapped"]) == {"remesh", "decimate", "uv_unwrap"}, h)
    with tempfile.TemporaryDirectory() as d:
        mods = fake_modules()
        canonical = mods["comfy_extras.nodes_mesh_postprocess"]
        canonical.__file__ = "/opt/comfyui/comfy_extras/nodes_mesh_postprocess.py"
        loaded = types.SimpleNamespace(**{k: v for k, v in vars(canonical).items()})
        mods["/opt/comfyui/comfy_extras/nodes_mesh_postprocess"] = loaded     # how ComfyUI names it
        mods["unrelated"] = types.SimpleNamespace(__file__="/elsewhere.py", _uv_unwrap=lambda: None)

        class Lazy:
            def __getattr__(self, name):
                raise ImportError("lazy module")
        mods["lazy"] = Lazy()
        try:
            h = P.install(mods, d, capture=False, counters=FakeCounters(), gtt_reader=lambda: 1)
        except Exception as exc:
            h = {"copies": {}, "raised": repr(exc)}
        check("install survives a module whose __getattr__ raises", "raised" not in h, h.get("raised"))
        check("every loaded copy of a target's file is wrapped",
              hasattr(loaded._uv_unwrap, "mem_probe_original") and hasattr(canonical._uv_unwrap, "mem_probe_original"))
        check("the header counts the copies", h["copies"].get("uv_unwrap") == 2 and h["copies"].get("pack") == 1, h["copies"])
        check("a module from another file is left alone", not hasattr(mods["unrelated"]._uv_unwrap, "mem_probe_original"))
        loaded._uv_unwrap(1)
        check("a call through the loaded copy is recorded",
              any(r.get("stage") == "uv_unwrap" for r in records(d)), [r.get("stage") for r in records(d)])
    os.environ.pop("MEM_PROBE_DIR", None)
    check("unset MEM_PROBE_DIR is not wanted", P.wanted() is False)
    os.environ["MEM_PROBE_DIR"] = "/tmp/x"
    check("a set MEM_PROBE_DIR is wanted", P.wanted() is True)
    os.environ.pop("MEM_PROBE_DIR")

    # capture: the first call's arguments, once, on the CPU
    with tempfile.TemporaryDirectory() as d:
        mods = fake_modules()
        P.install(mods, d, capture=True, counters=FakeCounters(), gtt_reader=lambda: 1)
        npp = mods["comfy_extras.nodes_mesh_postprocess"]
        first = torch.arange(6.0).reshape(2, 3)
        npp._uv_unwrap(first, torch.tensor([[0, 1, 1]]), "pec", 4096, 1, weld_distance=0.0002)
        saved = torch.load(os.path.join(d, "uv_unwrap_args.pt"))
        check("the first call's arguments are saved", torch.equal(saved["args"][0], first)
              and saved["args"][2:] == ("pec", 4096, 1) and saved["kwargs"] == {"weld_distance": 0.0002}, saved)
        npp._uv_unwrap(torch.zeros(1), torch.zeros(1), "adaptive", 1, 0)
        again = torch.load(os.path.join(d, "uv_unwrap_args.pt"))
        check("a second call does not overwrite them", again["args"][2] == "pec", again["args"][2:])
        check("only the capture stage captures", not os.path.exists(os.path.join(d, "remesh_args.pt")))

    print(f"{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all ok'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
