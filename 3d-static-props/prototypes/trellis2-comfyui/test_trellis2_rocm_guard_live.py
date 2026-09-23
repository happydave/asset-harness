"""The live gate for the ROCm GEMM guard (WI 1741): decode a saved TRELLIS.2 latent twice in one
process and require the reference vertex count and no non-finite vertex on both runs.

    cd /opt/comfyui && python /opt/comfyui/output/wi1613/test_trellis2_rocm_guard_live.py LATENT.pt [EXPECTED] [RUNS]

Runs inside the ComfyUI container (podman exec), where the guard is a custom node the checkout
carries. EXPECTED defaults to the fp16 reference for the WI 1613 crate latent; pass the fp32
figure for a --fp32-vae container. The pass is the count, not "no NaN": WI 1613 showed the
unguarded decode returning NaN-free meshes with the wrong population. Exit 1 on any run that
misses the count or carries a non-finite vertex; the failure names the run and the figures.
"""
import sys, time
sys.path.insert(0, "/opt/comfyui")
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
sys.argv = [sys.argv[0]]
latent_path = argv[0]
expected = int(argv[1]) if len(argv) > 1 else 6_481_922
runs = int(argv[2]) if len(argv) > 2 else 2
TOLERANCE = 0   # the guard's result is deterministic; the count is exact for a given VAE dtype

import asyncio  # noqa: E402
import torch  # noqa: E402
import folder_paths  # noqa: E402,F401
import nodes  # noqa: E402
import comfy.ldm.trellis2.vae as vae_mod  # noqa: E402
from comfy_extras import nodes_trellis2 as T  # noqa: E402

# Load the checkout's custom nodes the way the server does, so the guard's presence here is the
# container's real configuration and not this script's import.
asyncio.run(nodes.init_extra_nodes(init_custom_nodes=True, init_api_nodes=False))
guarded = getattr(vae_mod.SparseLinear, "rocm_gemm_guard_original", None) is not None
print(f"rocm_gemm_guard installed: {guarded}", flush=True)
vae = nodes.VAELoader().load_vae("trellis_2_shape_vae_bf16.safetensors")[0]
samples = torch.load(latent_path, map_location="cpu", weights_only=False)
failures = []
for r in range(1, runs + 1):
    t0 = time.time()
    with torch.inference_mode():
        out = T.VaeDecodeShapeTrellis.execute(samples, vae)
    mesh = out.args[0] if hasattr(out, "args") else out[0]
    verts = mesh.vertices
    if verts.dim() == 3:
        verts = verts[0]
    n = int(verts.shape[0])
    bad = int((~torch.isfinite(verts)).any(dim=1).sum().item())
    ok = abs(n - expected) <= TOLERANCE and bad == 0
    print(f"run {r}: {time.time()-t0:.1f}s vertices {n} (expected {expected}) nonfinite_vertices {bad} -> {'ok' if ok else 'FAIL'}", flush=True)
    if not ok:
        failures.append(r)
    torch.cuda.synchronize(); torch.cuda.empty_cache()
if failures:
    print(f"FAILED on runs {failures}: the decode is not the reference mesh", flush=True)
    sys.exit(1)
print("all runs at the reference count with no non-finite vertex", flush=True)
