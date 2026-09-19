import json, sys, urllib.request
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7121"
want = ["LoadImage","LoadBackgroundRemovalModel","RemoveBackground","ImageCropToMask",
        "CLIPVisionLoader","UNETLoader","ModelSamplingSD3","RescaleCFG","CFGOverride",
        "KSampler","VAELoader","VoxelToMesh","MeshToFile3D","GetMeshInfo",
        "Trellis2Conditioning","Pixal3DConditioning","Trellis2ShapeStage",
        "EmptyTrellis2LatentStructure","VaeDecodeShapeTrellis","VaeDecodeStructureTrellis2",
        "LoadMoGeModel","MoGeInference","MoGeGeometryToFOV","Save3DAdvanced"]
oi = json.load(urllib.request.urlopen(f"{BASE}/object_info", timeout=120))
missing = [w for w in want if w not in oi]
print("MISSING:", missing)
for w in want:
    if w not in oi: continue
    n = oi[w]
    print(f"--- {w}  -> outputs {n.get('output')}")
    for kind in ("required","optional"):
        for name, spec in (n["input"].get(kind) or {}).items():
            t = spec[0]
            extra = spec[1] if len(spec) > 1 else {}
            if isinstance(t, list):
                t = f"COMBO{t[:6]}"
            print(f"    {kind:8} {name}: {t} {json.dumps(extra)[:110] if extra else ''}")
