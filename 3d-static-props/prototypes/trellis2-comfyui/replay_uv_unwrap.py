#!/usr/bin/env python3
"""Replay UnwrapMesh's `_uv_unwrap` on a captured input, one call per process (asset-harness WI 1766).

Run in the lane image with the checkout at /opt/comfyui and both `rocm_unwrap_guard` and
`mem_probe` installed in its custom_nodes/:

    python replay_uv_unwrap.py CAPTURE.pt OUT_DIR --arm T|N [--layout]

Arm T expects the packer's torch path (numba absent), arm N its numba path (numba on PYTHONPATH).
The replay refuses (exit 2), naming what it saw, unless the guard is installed, the probe wrapped
every target, and the packer's numba flag matches the arm. It writes OUT_DIR/<arm>_<HHMMSS>_<pid>/: the
probe's stages.jsonl, result.json (per-stage records, GTT sampled every 0.1 s in-process, peak RSS,
output checks) and uv.npz (UVs and faces); with --layout also layout.png, the UV layout drawn as
triangle outlines.
"""
import argparse
import importlib.util
import json
import logging
import os
import resource
import sys
import threading
import time

COMFY = "/opt/comfyui"
sys.path.insert(0, COMFY)
os.chdir(COMFY)


def load_package(name):
    spec = importlib.util.spec_from_file_location(name, f"{COMFY}/custom_nodes/{name}/__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def has_guard(fn):
    """Whether rocm_unwrap_guard sits anywhere in the wrapper chain of `fn`."""
    while fn is not None:
        if getattr(fn, "rocm_unwrap_guard_original", None) is not None:
            return True
        fn = getattr(fn, "mem_probe_original", None)
    return False


class GttSampler(threading.Thread):
    def __init__(self, path, interval=0.1):
        super().__init__(daemon=True)
        self.path, self.interval, self.samples, self.stop = path, interval, [], threading.Event()

    def read(self):
        with open(self.path) as f:
            return int(f.read())

    def run(self):
        while not self.stop.is_set():
            self.samples.append((time.time(), self.read()))
            time.sleep(self.interval)


def draw_layout(uvs, faces, path, size=2048):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    px = uvs * (size - 1)
    px[:, 1] = (size - 1) - px[:, 1]
    for tri in px[faces]:
        draw.polygon([tuple(p) for p in tri], outline=(40, 60, 160))
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("out_dir")
    ap.add_argument("--arm", choices=("T", "N"), required=True)
    ap.add_argument("--layout", action="store_true")
    a = ap.parse_args()

    run_dir = os.path.join(a.out_dir, f"{a.arm}_{time.strftime('%H%M%S')}_{os.getpid()}")   # pid is 1 in a container
    os.makedirs(run_dir)
    logging.basicConfig(level=logging.INFO)
    unwrap_lines = []

    class Keep(logging.Handler):
        def emit(self, record):
            if "[uv_unwrap]" in record.getMessage():
                unwrap_lines.append(record.getMessage())
    logging.getLogger().addHandler(Keep())

    import numpy as np
    import torch
    import comfy.model_management as mm
    import comfy_extras.nodes_mesh_postprocess as npp
    from comfy_extras.mesh3d.uv_unwrap import pack as uv_pack, parameterize as uv_param

    os.environ.pop("MEM_PROBE_DIR", None)
    load_package("rocm_unwrap_guard")
    probe = load_package("mem_probe")
    header = probe.install(directory=run_dir, capture=False)

    want_numba = a.arm == "N"
    refusals = []
    if not has_guard(uv_param.lscm_charts_batch):
        refusals.append("rocm_unwrap_guard is not installed on lscm_charts_batch")
    if header["missing"] or len(header["wrapped"]) != len(probe.TARGETS):
        refusals.append(f"mem_probe wrapped {header['wrapped']}, missing {header['missing']}")
    if bool(uv_pack._HAVE_NUMBA_PACK) != want_numba:
        refusals.append(f"arm {a.arm} expects numba_pack={want_numba}, the packer has {uv_pack._HAVE_NUMBA_PACK}")
    if header["gtt_file"] is None:
        refusals.append(f"GTT unreadable: {header['gtt_unreadable']}")
    if refusals:
        print("REFUSED: " + "; ".join(refusals))
        return 2

    cap = torch.load(a.capture)
    device = mm.get_torch_device()
    args = list(cap["args"])
    if args[2] == "pec":                      # UnwrapMesh hands the pec segmenter device tensors
        args[0], args[1] = args[0].to(device), args[1].to(device)
    torch.cuda.synchronize()

    sampler = GttSampler(header["gtt_file"])
    base = sampler.read()
    sampler.start()
    t0 = time.time()
    vmapping, indices, uvs = npp._uv_unwrap(*args, **cap["kwargs"])
    wall = time.time() - t0
    torch.cuda.synchronize()
    sampler.stop.set()
    sampler.join()

    with open(os.path.join(run_dir, "stages.jsonl")) as f:
        stages = [json.loads(line) for line in f if '"header"' not in line]
    peak = max(v for _, v in sampler.samples)
    gaps = np.diff([t for t, _ in sampler.samples])
    mib = 1 << 20
    result = {
        "arm": a.arm, "numba_pack": bool(uv_pack._HAVE_NUMBA_PACK), "wall_s": round(wall, 2),
        "gtt_base_mib": base // mib, "gtt_peak_mib": peak // mib, "gtt_rise_mib": (peak - base) // mib,
        "samples": len(sampler.samples), "sample_interval_s": round(float(gaps.mean()), 4) if gaps.size else None,
        "rss_max_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
        "stages": [{k: s[k] for k in ("stage", "demand", "cache_growth", "peak_alloc", "peak_res",
                                      "alloc_enter", "res_enter", "t_enter", "t_exit", "ok")} for s in stages],
        "n_uv": int(uvs.shape[0]), "n_vmap": int(vmapping.shape[0]), "n_faces": int(indices.shape[0]),
        "uv_finite": bool(np.isfinite(uvs).all()),
        "uv_in_unit": bool(((uvs >= 0) & (uvs <= 1)).all()),
        "faces_in_range": bool(indices.min() >= 0 and indices.max() < uvs.shape[0]),
        "unwrap_log": unwrap_lines,
    }
    np.savez_compressed(os.path.join(run_dir, "uv.npz"), uvs=uvs, faces=indices)
    if a.layout:
        draw_layout(uvs, indices, os.path.join(run_dir, "layout.png"))
    with open(os.path.join(run_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=1)
    by_stage = {s["stage"]: s for s in result["stages"]}
    pk = by_stage.get("pack", {})
    print(f"RESULT arm={a.arm} numba={result['numba_pack']} wall={result['wall_s']}s "
          f"gtt_rise={result['gtt_rise_mib']}MiB pack_demand={pk.get('demand', 0) // mib}MiB "
          f"pack_cache_growth={pk.get('cache_growth', 0) // mib}MiB rss_max={result['rss_max_mib']}MiB "
          f"uv_ok={result['uv_finite'] and result['uv_in_unit'] and result['faces_in_range']} dir={run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
