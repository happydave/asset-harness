"""Drop NaN/inf vertices (and any face touching one) and rewrite a clean GLB.

The point is not to ship a repair step; it is to make the artifact viewable so the
'is it recognisable' check can run at all.
"""
import json, struct, sys
import numpy as np

src, dst = sys.argv[1], sys.argv[2]
with open(src, "rb") as f:
    magic, version, length = struct.unpack("<III", f.read(12))
    chunks = []
    while f.tell() < length:
        clen, ctype = struct.unpack("<II", f.read(8))
        chunks.append((ctype, f.read(clen)))
js = json.loads(next(d for t, d in chunks if t == 0x4E4F534A).decode("utf-8"),
                parse_constant=lambda c: float("nan"))
blob = next(d for t, d in chunks if t == 0x004E4942)

prim = js["meshes"][0]["primitives"][0]
pa = js["accessors"][prim["attributes"]["POSITION"]]
ia = js["accessors"][prim["indices"]]
pv = js["bufferViews"][pa["bufferView"]]
iv = js["bufferViews"][ia["bufferView"]]

pos = np.frombuffer(blob, dtype="<f4", count=pa["count"] * 3,
                    offset=pv.get("byteOffset", 0) + pa.get("byteOffset", 0)).reshape(-1, 3)
idt = {5121: "<u1", 5123: "<u2", 5125: "<u4"}[ia["componentType"]]
idx = np.frombuffer(blob, dtype=idt, count=ia["count"],
                    offset=iv.get("byteOffset", 0) + ia.get("byteOffset", 0)).reshape(-1, 3)

good = np.isfinite(pos).all(axis=1)
print(f"vertices {pos.shape[0]}  bad {int((~good).sum())} ({100*(~good).mean():.3f}%)")
keep_face = good[idx].all(axis=1)
print(f"faces    {idx.shape[0]}  dropped {int((~keep_face).sum())} ({100*(~keep_face).mean():.3f}%)")

remap = np.full(pos.shape[0], -1, dtype=np.int64)
used = np.unique(idx[keep_face])
remap[used] = np.arange(used.size)
new_pos = pos[used].astype("<f4")
new_idx = remap[idx[keep_face]].astype("<u4")
print(f"kept     {new_pos.shape[0]} vertices, {new_idx.shape[0]} faces")
print(f"bbox     min={new_pos.min(axis=0).tolist()} max={new_pos.max(axis=0).tolist()}")

pb, ib = new_pos.tobytes(), new_idx.tobytes()
pad = lambda b, n=4: b + b"\x00" * ((-len(b)) % n)
buf = pad(pb) + pad(ib)
out = {
  "asset": {"version": "2.0", "generator": "wi1600 glb_repair"},
  "scenes": [{"nodes": [0]}], "scene": 0, "nodes": [{"mesh": 0}],
  "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
  "buffers": [{"byteLength": len(buf)}],
  "bufferViews": [
      {"buffer": 0, "byteOffset": 0, "byteLength": len(pb), "target": 34962},
      {"buffer": 0, "byteOffset": len(pad(pb)), "byteLength": len(ib), "target": 34963}],
  "accessors": [
      {"bufferView": 0, "componentType": 5126, "count": int(new_pos.shape[0]), "type": "VEC3",
       "min": new_pos.min(axis=0).tolist(), "max": new_pos.max(axis=0).tolist()},
      {"bufferView": 1, "componentType": 5125, "count": int(new_idx.size), "type": "SCALAR"}],
}
jb = pad(json.dumps(out).encode(), 4) if False else json.dumps(out).encode()
jb = jb + b" " * ((-len(jb)) % 4)
with open(dst, "wb") as f:
    f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(jb) + 8 + len(buf)))
    f.write(struct.pack("<II", len(jb), 0x4E4F534A)); f.write(jb)
    f.write(struct.pack("<II", len(buf), 0x004E4942)); f.write(buf)
print("wrote", dst)
