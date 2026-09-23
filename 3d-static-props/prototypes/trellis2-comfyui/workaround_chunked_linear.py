"""WI 1613 workaround test: run the shape decode with every Linear in the decoder applied in row
chunks of at most 2^20, the row count above which the ROCm GEMM returns wrong results for a small N.

    cd /opt/comfyui && python /opt/comfyui/output/wi1613/workaround_chunked_linear.py LATENT.pt [RUNS]

Prints vertices and non-finite vertices per run; the pass is the CPU/CUDA reference count
(~6.48 M for the crate latent), the same on every run.
"""
import sys, time
sys.path.insert(0, "/opt/comfyui")
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
sys.argv = [sys.argv[0]]
latent_path = argv[0]
runs = int(argv[1]) if len(argv) > 1 else 4
CHUNK = 1 << 20

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
import folder_paths  # noqa: E402,F401
import nodes  # noqa: E402
from comfy_extras import nodes_trellis2 as T  # noqa: E402

vae = nodes.VAELoader().load_vae("trellis_2_shape_vae_bf16.safetensors")[0]
dec = vae.first_stage_model.shape_dec
samples = torch.load(latent_path, map_location="cpu", weights_only=False)

patched = 0
for name, mod in dec.named_modules():
    if isinstance(mod, torch.nn.Linear):
        orig = mod.forward

        def chunked_forward(inp, _orig=orig):
            feats = inp.feats if hasattr(inp, "feats") else inp
            if feats.shape[0] <= CHUNK:
                return _orig(inp)
            parts = [_orig(inp.replace(feats[s:s + CHUNK]) if hasattr(inp, "feats") else feats[s:s + CHUNK])
                     for s in range(0, feats.shape[0], CHUNK)]
            if hasattr(inp, "feats"):
                return inp.replace(torch.cat([p.feats for p in parts], dim=0))
            return torch.cat(parts, dim=0)

        mod.forward = chunked_forward
        patched += 1
print(f"patched {patched} Linear modules to row chunks of {CHUNK}", flush=True)
for r in range(1, runs + 1):
    t0 = time.time()
    with torch.inference_mode():
        out = T.VaeDecodeShapeTrellis.execute(samples, vae)
    mesh = out.args[0] if hasattr(out, "args") else out[0]
    verts = mesh.vertices
    if verts.dim() == 3:
        verts = verts[0]
    bad = int((~torch.isfinite(verts)).any(dim=1).sum().item())
    print(f"run {r}: {time.time()-t0:.1f}s vertices {int(verts.shape[0])} nonfinite_vertices {bad}", flush=True)
    torch.cuda.synchronize(); torch.cuda.empty_cache()
