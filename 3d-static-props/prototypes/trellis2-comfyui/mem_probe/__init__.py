"""Per-stage memory probe for the lane's mesh tail (asset-harness WI 1766).

A ComfyUI custom-node package that registers no nodes. With MEM_PROBE_DIR set, it wraps the mesh
post-process stages named in TARGETS and appends one JSON record per call to
$MEM_PROBE_DIR/stages.jsonl: torch's allocated and reserved bytes at entry and exit, the peaks during
the call, and the device's GTT use from sysfs. With MEM_PROBE_CAPTURE=1 it also saves the first
`_uv_unwrap` call's arguments to $MEM_PROBE_DIR/uv_unwrap_args.pt for replay_uv_unwrap.py. A wrapped
stage returns and raises exactly what the original does. With MEM_PROBE_DIR unset it wraps nothing.
Install by copying this directory into the checkout's `custom_nodes/` (install.sh).
"""
import functools
import glob
import importlib
import json
import logging
import os
import sys
import time

import torch

_log = logging.getLogger("mem_probe")

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

TARGETS = (  # (stage, module, attribute); every call site resolves these names at call time
    ("remesh", "comfy_extras.nodes_mesh_postprocess", "remesh_narrow_band_dc"),
    ("decimate", "comfy_extras.nodes_mesh_postprocess", "qem_decimate_simplify"),
    ("uv_unwrap", "comfy_extras.nodes_mesh_postprocess", "_uv_unwrap"),
    ("lscm_batch", "comfy_extras.mesh3d.uv_unwrap.parameterize", "lscm_charts_batch"),
    ("pack", "comfy_extras.mesh3d.uv_unwrap.pack", "pack_bitmap_concat"),
    ("apply", "comfy_extras.mesh3d.uv_unwrap.pack", "apply_placements_concat"),
)
CAPTURE_STAGE = "uv_unwrap"


def wanted() -> bool:
    return bool(os.environ.get("MEM_PROBE_DIR"))


def out_dir() -> str:
    return os.environ["MEM_PROBE_DIR"]


class TorchCounters:
    """torch's caching-allocator counters for the current device; zeros without a GPU."""
    def __init__(self):
        self.live = torch.cuda.is_available()

    def allocated(self):
        return torch.cuda.memory_allocated() if self.live else 0

    def reserved(self):
        return torch.cuda.memory_reserved() if self.live else 0

    def peaks(self):
        return (torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved()) if self.live else (0, 0)

    def reset_peaks(self):
        if self.live:
            torch.cuda.reset_peak_memory_stats()


def _gtt_path():
    """The first readable GTT counter in sysfs, or (None, why not)."""
    reason = "no mem_info_gtt_used under /sys/class/drm"
    for path in sorted(glob.glob("/sys/class/drm/card*/device/mem_info_gtt_used")):
        try:
            with open(path) as f:
                int(f.read())
            return path, None
        except (OSError, ValueError) as exc:
            reason = f"{path}: {exc}"
    return None, reason


def _file_reader(path):
    def read():
        with open(path) as f:
            return int(f.read())
    return read


class Probe:
    """Records stage calls. Peaks are folded into every open stage at each boundary, so an outer
    stage's peak covers the stages nested inside it even though the counters are reset at each."""
    def __init__(self, sink, counters=None, gtt_reader=None):
        self.sink = sink                  # callable taking one record dict
        self.counters = counters or TorchCounters()
        self.gtt = gtt_reader or (lambda: None)
        self._open = []                   # [peak_allocated, peak_reserved] per open stage

    def _fold(self):
        pa, pr = self.counters.peaks()
        for frame in self._open:
            frame[0] = max(frame[0], pa)
            frame[1] = max(frame[1], pr)
        self.counters.reset_peaks()

    def wrap(self, stage, original, on_call=None):
        @functools.wraps(original)
        def call(*args, **kwargs):
            if on_call is not None:
                try:
                    on_call(args, kwargs)
                except Exception as exc:  # the probe must not change the stage's outcome
                    _log.warning("mem_probe: %s hook failed: %r", stage, exc)
            self._fold()
            a0, r0, g0, t0 = self.counters.allocated(), self.counters.reserved(), self.gtt(), time.time()
            frame = [a0, r0]
            self._open.append(frame)
            error = None
            try:
                return original(*args, **kwargs)
            except BaseException as exc:
                error = repr(exc)[:300]
                raise
            finally:
                self._fold()
                del self._open[next(i for i, f in enumerate(self._open) if f is frame)]
                self._emit({
                    "stage": stage, "pid": os.getpid(), "t_enter": t0, "t_exit": time.time(),
                    "alloc_enter": a0, "res_enter": r0,
                    "alloc_exit": self.counters.allocated(), "res_exit": self.counters.reserved(),
                    "peak_alloc": frame[0], "peak_res": frame[1],
                    "demand": frame[0] - a0, "cache_growth": frame[1] - r0,
                    "gtt_enter": g0, "gtt_exit": self.gtt(),
                    "wraps_unwrap_guard": getattr(original, "rocm_unwrap_guard_original", None) is not None,
                    "ok": error is None, "error": error,
                })
        call.mem_probe_original = original
        return call

    def _emit(self, record):
        try:
            self.sink(record)
        except Exception as exc:  # a lost record must not change the stage's outcome
            _log.warning("mem_probe: record for %s not written: %r", record.get("stage"), exc)


def _cpu_copy(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, (list, tuple)):
        return type(value)(_cpu_copy(v) for v in value)
    if isinstance(value, dict):
        return {k: _cpu_copy(v) for k, v in value.items()}
    return value


def capturer(path):
    """on_call hook: save the first call's arguments to `path`; later calls leave it alone."""
    def on_call(args, kwargs):
        if not os.path.exists(path):
            torch.save({"args": _cpu_copy(args), "kwargs": _cpu_copy(kwargs)}, path)
    return on_call


def jsonl_sink(path):
    def sink(record):
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    return sink


def module_copies(mod_name, registry, canonical):
    """Every loaded module object for the target's source file. ComfyUI loads its built-in node
    files under their path as the module name, so a normal import yields a second copy that the
    registered node classes never call."""
    path = getattr(canonical, "__file__", None)
    copies = [canonical]
    for m in list(registry.values()):
        try:
            same = m is not canonical and path is not None and getattr(m, "__file__", None) == path
        except Exception:  # a lazy module's __getattr__ can import or raise; it is not a copy
            same = False
        if same:
            copies.append(m)
    return copies


def install(modules=None, directory=None, capture=None, counters=None, gtt_reader=None) -> dict:
    """Wrap every target that exists, in every loaded copy of its module; idempotent. Returns (and
    records) a header naming what was wrapped and in how many copies, what was already wrapped, what
    is missing, the packer's numba flag and sysfs state. `modules` stands in for sys.modules
    (tests); by default targets are imported and sys.modules is scanned."""
    directory = directory or out_dir()
    os.makedirs(directory, exist_ok=True)
    sink = jsonl_sink(os.path.join(directory, "stages.jsonl"))
    if capture is None:
        capture = os.environ.get("MEM_PROBE_CAPTURE") == "1"
    gtt_file, gtt_unreadable = None, None
    if gtt_reader is None:
        gtt_file, gtt_unreadable = _gtt_path()
        gtt_reader = _file_reader(gtt_file) if gtt_file else None
    probe = Probe(sink, counters, gtt_reader)
    header = {"header": True, "pid": os.getpid(), "wrapped": [], "already": [], "missing": [],
              "copies": {}, "gtt_file": gtt_file, "gtt_unreadable": gtt_unreadable, "numba_pack": None,
              "capture": capture}
    registry = modules if modules is not None else sys.modules
    for stage, mod_name, attr in TARGETS:
        try:
            mod = modules[mod_name] if modules is not None else importlib.import_module(mod_name)
        except (KeyError, ImportError) as exc:
            header["missing"].append(f"{stage}: {mod_name} ({exc.__class__.__name__})")
            continue
        if getattr(mod, attr, None) is None:
            header["missing"].append(f"{stage}: {mod_name}.{attr}")
            continue
        hook = capturer(os.path.join(directory, "uv_unwrap_args.pt")) if capture and stage == CAPTURE_STAGE else None
        wrapped = 0
        for copy in module_copies(mod_name, registry, mod):
            current = getattr(copy, attr, None)
            if current is None or getattr(current, "mem_probe_original", None) is not None:
                continue
            setattr(copy, attr, probe.wrap(stage, current, hook))
            wrapped += 1
        if wrapped:
            header["wrapped"].append(stage)
            header["copies"][stage] = wrapped
        else:
            header["already"].append(stage)
        if stage == "pack":
            header["numba_pack"] = getattr(mod, "_HAVE_NUMBA_PACK", None)
    sink(header)
    return header


if wanted():
    _header = install()
    _log.info("mem_probe: wrapped %s in %s module copies; missing %s; numba_pack=%s; records in %s",
              _header["wrapped"], _header["copies"], _header["missing"], _header["numba_pack"], out_dir())
