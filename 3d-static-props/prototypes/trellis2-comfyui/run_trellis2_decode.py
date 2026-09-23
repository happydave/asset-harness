"""Run the TRELLIS.2 geometry path on one image at a chosen decode resolution, and census the GLB.

    python3 run_trellis2_decode.py IMAGE DECODE PREFIX [BASE] [SEED_SS] [SEED_SHAPE]

DECODE is 512 (decode the shape-stage latent directly, no upsample stage) or an upsample target
(1024 … 2048, step 128). The graph is run_trellis2.py's with the decode wired to the chosen
latent; node ids still mirror the shipped template. BASE defaults to the WI 1600 container's
loopback port. On completion the saved GLB's position buffers are counted for non-finite floats.

Built for WI 1613: the NaN in VaeDecodeShapeTrellis has only been measured at 1536, which a 12 GiB
card cannot hold, so the ROCm and CUDA arms need a resolution both cards can run.
"""
import json, os, sys, time, urllib.request, urllib.error, glob, array, math
try:
    import numpy as np
except ImportError:  # the host python on ai2 has no numpy; the pure-Python walk is slower but exact
    np = None

image = sys.argv[1]
decode = int(sys.argv[2])
prefix = sys.argv[3]
BASE = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:7121"
seed_ss = int(sys.argv[5]) if len(sys.argv) > 5 else 56
seed_shape = int(sys.argv[6]) if len(sys.argv) > 6 else 42
unet = "trellis_2_int8_convrot.safetensors"

G = {
  "122": {"class_type": "LoadImage", "inputs": {"image": image}},
  "193": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}},
  "192": {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": ["193", 0], "image": ["122", 0]}},
  "312": {"class_type": "ImageCropToMask", "inputs": {
      "images": ["122", 0], "masks": ["192", 0],
      "width": 1024, "height": 1024, "pad_factor": 1.1, "grow_mask": 0, "background": "#000000"}},
  "15":  {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "dino_v3_L_naf_fp32.safetensors"}},
  "299": {"class_type": "Trellis2Conditioning", "inputs": {"clip_vision_model": ["15", 0], "image": ["312", 0]}},
  "40":  {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
  "199": {"class_type": "CFGOverride", "inputs": {"model": ["40", 0], "cfg": 1, "start_percent": 0.667, "end_percent": 1}},
  "125": {"class_type": "RescaleCFG", "inputs": {"model": ["199", 0], "multiplier": 0.7}},
  "108": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["125", 0], "shift": 5}},
  "279": {"class_type": "CFGOverride", "inputs": {"model": ["40", 0], "cfg": 1, "start_percent": 0.769, "end_percent": 1}},
  "126": {"class_type": "RescaleCFG", "inputs": {"model": ["279", 0], "multiplier": 0.5}},
  "117": {"class_type": "VAELoader", "inputs": {"vae_name": "trellis_2_shape_vae_bf16.safetensors"}},
  "87":  {"class_type": "EmptyTrellis2LatentStructure", "inputs": {"batch_size": 1}},
  "3":   {"class_type": "KSampler", "inputs": {"model": ["108", 0], "seed": seed_ss, "steps": 12, "cfg": 7.5,
          "sampler_name": "euler", "scheduler": "normal", "positive": ["299", 0], "negative": ["299", 1],
          "latent_image": ["87", 0], "denoise": 1}},
  "119": {"class_type": "VaeDecodeStructureTrellis2", "inputs": {"samples": ["3", 0], "vae": ["117", 0], "resolution": "32"}},
  "91":  {"class_type": "Trellis2ShapeStage", "inputs": {"positive": ["299", 0], "negative": ["299", 1], "voxel": ["119", 0]}},
  "18":  {"class_type": "KSampler", "inputs": {"model": ["126", 0], "seed": seed_shape, "steps": 20, "cfg": 7.5,
          "sampler_name": "euler", "scheduler": "normal", "positive": ["91", 0], "negative": ["91", 1],
          "latent_image": ["91", 2], "denoise": 1}},
}
if decode == 512:
    decode_src = ["18", 0]
else:
    G["94"] = {"class_type": "Trellis2UpsampleStage", "inputs": {"positive": ["91", 0], "negative": ["91", 1],
               "shape_latent": ["18", 0], "vae": ["117", 0], "target_resolution": decode}}
    G["23"] = {"class_type": "KSampler", "inputs": {"model": ["126", 0], "seed": seed_shape, "steps": 12, "cfg": 7.5,
               "sampler_name": "euler", "scheduler": "simple", "positive": ["94", 0], "negative": ["94", 1],
               "latent_image": ["94", 2], "denoise": 1}}
    decode_src = ["23", 0]
G["92"] = {"class_type": "VaeDecodeShapeTrellis", "inputs": {"samples": decode_src, "vae": ["117", 0]}}
G["202"] = {"class_type": "GetMeshInfo", "inputs": {"mesh": ["92", 0]}}
G["285"] = {"class_type": "MeshToFile3D", "inputs": {"mesh": ["202", 0]}}
G["322"] = {"class_type": "Save3DAdvanced", "inputs": {"model_3d": ["285", 0], "filename_prefix": prefix,
            "viewport_state": "", "width": 1024, "height": 1024}}

req = urllib.request.Request(f"{BASE}/prompt", method="POST",
        data=json.dumps({"prompt": G, "client_id": "wi1613"}).encode(),
        headers={"Content-Type": "application/json"})
try:
    resp = json.load(urllib.request.urlopen(req, timeout=60))
except urllib.error.HTTPError as e:
    print("VALIDATION FAILED:", json.dumps(json.loads(e.read().decode()), indent=2)[:4000])
    raise SystemExit(2)
pid = resp["prompt_id"]
print("PROMPT_ID", pid, "decode", decode, "seeds", seed_ss, seed_shape, flush=True)
t0 = time.time()
while True:
    time.sleep(10)
    h = json.load(urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=30))
    if pid in h:
        st = h[pid]["status"]
        print(f"DONE status={st.get('status_str')} completed={st.get('completed')} elapsed={time.time()-t0:.0f}s", flush=True)
        outs = h[pid].get("outputs", {})
        print("OUTPUTS", json.dumps(outs)[:1500], flush=True)
        for m in st.get("messages", [])[-6:]:
            print("MSG", json.dumps(m)[:500], flush=True)
        cached = h[pid].get("meta", {})
        break
    if time.time() - t0 > 5400:
        print("TIMEOUT after 90min", flush=True); raise SystemExit(3)

# --- census of the saved GLB (the same walk as glb_probe.py, kept inline so one command answers) ---
def census(path):
    import struct
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        assert magic == 0x46546C67, "not a GLB"
        chunks = []
        while f.tell() < length:
            clen, ctype = struct.unpack("<II", f.read(8))
            chunks.append((ctype, f.read(clen)))
    js_raw = next(d for t, d in chunks if t == 0x4E4F534A)
    bin_raw = next((d for t, d in chunks if t == 0x004E4942), b"")
    txt = js_raw.decode("utf-8", "replace")
    g = json.loads(txt, parse_constant=lambda c: float("nan") if "NaN" in c else float("inf"))
    NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    out = {"file": path, "size_mb": round(length / 1e6, 1), "json_nan_literals": txt.count("NaN")}
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            ai = prim["attributes"].get("POSITION")
            if ai is None:
                continue
            acc = g["accessors"][ai]
            bv = g["bufferViews"][acc["bufferView"]]
            off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            n = acc["count"] * NCOMP[acc["type"]]
            if np is not None:
                arr = np.frombuffer(bin_raw, dtype="<f4", count=n, offset=off)
                nan = int(np.isnan(arr).sum()); inf = int(np.isinf(arr).sum())
                v = arr.reshape(-1, 3)
                bad_v = int(np.any(~np.isfinite(v), axis=1).sum())
                finite = arr[np.isfinite(arr)]
                size, nverts = int(arr.size), int(v.shape[0])
                rng = [float(finite.min()), float(finite.max())] if finite.size else None
            else:
                a = array.array("f"); a.frombytes(bin_raw[off:off + 4 * n])
                if sys.byteorder != "little":
                    a.byteswap()
                nan = inf = bad_v = 0; lo = math.inf; hi = -math.inf
                for i in range(0, len(a), 3):
                    bad = False
                    for x in (a[i], a[i + 1], a[i + 2]):
                        if x != x:
                            nan += 1; bad = True
                        elif x in (math.inf, -math.inf):
                            inf += 1; bad = True
                        else:
                            lo = x if x < lo else lo; hi = x if x > hi else hi
                    bad_v += bad
                size, nverts = len(a), len(a) // 3
                rng = [lo, hi] if lo <= hi else None
            out.update({"position_floats": size, "nan_floats": nan, "inf_floats": inf,
                        "nan_pct": round(100 * nan / size, 3), "vertices": nverts,
                        "nonfinite_vertices": bad_v, "nonfinite_vertex_pct": round(100 * bad_v / nverts, 3),
                        "finite_range": rng})
    return out

found = []
for node in outs.values():
    for item in node.get("3d", []) + node.get("result", []) if isinstance(node, dict) else []:
        if isinstance(item, dict) and item.get("filename", "").endswith(".glb"):
            found.append(os.path.join(os.environ.get("COMFY_OUTPUT", os.path.expanduser("~/wi1600/output")),
                                      item.get("subfolder", ""), item["filename"]))
if not found:
    pat = os.path.join(os.environ.get("COMFY_OUTPUT", os.path.expanduser("~/wi1600/output")), prefix + "*.glb")
    found = sorted(glob.glob(pat), key=os.path.getmtime)[-1:]
for p in found:
    print("CENSUS", json.dumps(census(p)), flush=True)
