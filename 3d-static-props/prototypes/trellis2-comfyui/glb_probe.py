"""Probe a GLB for NaN/inf: in the JSON chunk, and in the actual vertex buffers."""
import json, struct, sys, math
import numpy as np

path = sys.argv[1]
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
print(f"file={path} size={length/1e6:.1f} MB  json={len(js_raw)}B bin={len(bin_raw)/1e6:.1f} MB")
for tok in ("NaN", "Infinity", "-Infinity"):
    print(f"  JSON literal {tok!r}: {txt.count(tok)} occurrences")

g = json.loads(txt, parse_constant=lambda c: float("nan") if "NaN" in c else float("inf"))
print(f"  meshes={len(g.get('meshes',[]))} accessors={len(g.get('accessors',[]))}")
for i, acc in enumerate(g.get("accessors", [])):
    mn, mx = acc.get("min"), acc.get("max")
    bad = any(v != v or math.isinf(v) for v in (mn or []) + (mx or []))
    if bad or i < 4:
        print(f"  accessor[{i}] type={acc.get('type')} count={acc.get('count')} min={mn} max={mx} {'<-- NaN/inf' if bad else ''}")

COMP = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
for mi, mesh in enumerate(g.get("meshes", [])):
    for pi, prim in enumerate(mesh.get("primitives", [])):
        for name, ai in prim.get("attributes", {}).items():
            acc = g["accessors"][ai]
            if acc["componentType"] != 5126:
                continue
            bv = g["bufferViews"][acc["bufferView"]]
            off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            n = acc["count"] * NCOMP[acc["type"]]
            arr = np.frombuffer(bin_raw, dtype="<f4", count=n, offset=off)
            nan = int(np.isnan(arr).sum()); inf = int(np.isinf(arr).sum())
            finite = arr[np.isfinite(arr)]
            rng = (float(finite.min()), float(finite.max())) if finite.size else (None, None)
            print(f"  mesh{mi}.prim{pi}.{name}: n={arr.size} NaN={nan} ({100*nan/arr.size:.2f}%) inf={inf} finite_range={rng}")
