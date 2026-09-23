"""Decode a saved TRELLIS.2 latent through VaeDecodeShapeTrellis with forward hooks on every module
of the shape decoder, and name the first module whose output carries a non-finite value.

    cd /opt/comfyui && python /opt/comfyui/output/wi1613/bisect_decode.py LATENT.pt [RUNS] [--cpu]

Runs inside the ComfyUI container (imports ComfyUI's own loader and node), so the decode is the
one the graph runs. Each run prints: device, dtype, the first offending module in call order with
whether its inputs were already non-finite (propagating) or finite (producing), and the mesh's
vertex count and non-finite vertex count. Repeat RUNS times in one process because the ROCm decode
is non-deterministic (WI 1613). Spike scaffolding, not production.
"""
import sys, os, time
sys.path.insert(0, "/opt/comfyui")
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
CPU = "--cpu" in sys.argv
if CPU:
    sys.argv = [sys.argv[0], "--cpu"]
else:
    sys.argv = [sys.argv[0]]
latent_path = argv[0]
runs = int(argv[1]) if len(argv) > 1 else 3

import torch  # noqa: E402
import folder_paths  # noqa: E402,F401
import nodes  # noqa: E402
from comfy_extras import nodes_trellis2 as T  # noqa: E402
import comfy.model_management as mm  # noqa: E402


def nonfinite(x):
    """Count of non-finite floats in a tensor-ish output, or None when it carries no float tensor."""
    if torch.is_tensor(x):
        return int((~torch.isfinite(x)).sum().item()) if x.is_floating_point() else None
    if hasattr(x, "feats"):
        return nonfinite(x.feats)
    if isinstance(x, (tuple, list)):
        vals = [nonfinite(v) for v in x]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None
    return None


vae = nodes.VAELoader().load_vae("trellis_2_shape_vae_bf16.safetensors")[0]
dec = vae.first_stage_model.shape_dec
samples = torch.load(latent_path, map_location="cpu", weights_only=False)

events = []
def make_hook(name):
    def hook(mod, inputs, output):
        n_in = nonfinite(inputs)
        n_out = nonfinite(output)
        if n_out:
            events.append((name, n_in or 0, n_out))
    return hook

handles = [m.register_forward_hook(make_hook(n)) for n, m in dec.named_modules() if n]
print(f"device {mm.get_torch_device()} vae_dtype {vae.vae_dtype} modules hooked {len(handles)}", flush=True)

for r in range(1, runs + 1):
    events.clear()
    t0 = time.time()
    with torch.inference_mode():   # the graph executor runs nodes without autograd; so must this
        out = T.VaeDecodeShapeTrellis.execute(samples, vae)
    mesh = out.args[0] if hasattr(out, "args") else out[0]   # IO.NodeOutput(mesh, subs); mesh is Types.MESH
    verts = getattr(mesh, "vertices", None)
    if verts is None and isinstance(mesh, dict):
        verts = mesh.get("vertices")
    if verts is not None and verts.dim() == 3:
        verts = verts[0]
    nv = int(verts.shape[0]) if verts is not None else -1
    bad = int((~torch.isfinite(verts)).any(dim=1).sum().item()) if verts is not None else -1
    first = events[0] if events else None
    producing = [e for e in events if e[1] == 0]
    print(f"run {r}: {time.time()-t0:.1f}s vertices {nv} nonfinite_vertices {bad} "
          f"first_nonfinite_module {first[0] if first else 'none'} "
          f"(inputs_nonfinite {first[1] if first else 0}, outputs_nonfinite {first[2] if first else 0}) "
          f"producing_modules {[e[0] for e in producing][:4]} total_events {len(events)}", flush=True)
    if not CPU:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
for h in handles:
    h.remove()
