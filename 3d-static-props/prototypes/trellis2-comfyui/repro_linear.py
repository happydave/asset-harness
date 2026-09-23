"""Isolate the matmul WI 1613's bisect named: capture the fp16 input to the shape decoder's
`blocks.3.4.to_subdiv` Linear during one real decode, then run that one matmul repeatedly on the
GPU in fp16 / bf16 / fp32 and count non-finite outputs.

    cd /opt/comfyui && python /opt/comfyui/output/wi1613/repro_linear.py LATENT.pt [REPEATS]

Also writes the captured activation and weight to OUTDIR/to_subdiv_input.pt so the matmul can be
re-run on another vendor, and reports the smallest row block that still produces a non-finite
value, for a reproducer small enough to share. Spike scaffolding, not production.
"""
import sys, os, time
sys.path.insert(0, "/opt/comfyui")
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
sys.argv = [sys.argv[0]]
latent_path = argv[0]
repeats = int(argv[1]) if len(argv) > 1 else 10
OUTDIR = os.path.dirname(latent_path)

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
import folder_paths  # noqa: E402,F401
import nodes  # noqa: E402
from comfy_extras import nodes_trellis2 as T  # noqa: E402

vae = nodes.VAELoader().load_vae("trellis_2_shape_vae_bf16.safetensors")[0]
dec = vae.first_stage_model.shape_dec
samples = torch.load(latent_path, map_location="cpu", weights_only=False)
target = dict(dec.named_modules())["blocks.3.4.to_subdiv"]
captured = {}


def hook(mod, inputs, output):
    x = inputs[0]
    feats = x.feats if hasattr(x, "feats") else x
    if "x" not in captured:
        captured["x"] = feats.detach().clone()
        captured["y"] = (output.feats if hasattr(output, "feats") else output).detach().clone()
        captured["w"] = mod.weight.detach().clone()
        captured["b"] = mod.bias.detach().clone() if mod.bias is not None else None


h = target.register_forward_hook(hook)
with torch.inference_mode():
    T.VaeDecodeShapeTrellis.execute(samples, vae)
h.remove()
x, y, w, b = captured["x"], captured["y"], captured["w"], captured["b"]
print(f"captured x {tuple(x.shape)} {x.dtype} {x.device} finite={bool(torch.isfinite(x).all())} "
      f"|x|max={x.float().abs().max().item():.3f}  w {tuple(w.shape)} {w.dtype} |w|max={w.float().abs().max().item():.3f} "
      f"b {None if b is None else tuple(b.shape)}  decode output non-finite={int((~torch.isfinite(y)).sum())}", flush=True)
torch.save({"x": x.cpu(), "w": w.cpu(), "b": None if b is None else b.cpu()}, os.path.join(OUTDIR, "to_subdiv_input.pt"))


ref = F.linear(x.cpu().float(), w.cpu().float(), None if b is None else b.cpu().float())


def count(dtype, fn, label):
    """Non-finite count per run, how many elements differ from the first run (bitwise), and the
    worst absolute deviation from the CPU fp32 reference over the finite elements."""
    xs, ws, bs = x.to(dtype), w.to(dtype), (None if b is None else b.to(dtype))
    bad, differ, dev = [], [], []
    first = None
    for _ in range(repeats):
        out = fn(xs, ws, bs)
        torch.cuda.synchronize()
        bad.append(int((~torch.isfinite(out)).sum().item()))
        if first is None:
            first = out.clone()
        differ.append(int((out != first).sum().item()))
        o = out.float().cpu()
        fin = torch.isfinite(o)
        dev.append(round(float((o[fin] - ref[fin]).abs().max()), 4) if fin.any() else None)
    print(f"  {label:<20} {str(dtype):<14} non-finite/run {bad}  elements differing from run 1 {differ}  "
          f"max|dev| from CPU fp32 {dev}", flush=True)
    return bad


with torch.inference_mode():
    print("GPU, the same matmul, repeated:")
    for dtype in (torch.float16, torch.bfloat16, torch.float32):
        count(dtype, lambda a, ww, bb: F.linear(a, ww, bb), "F.linear")
        count(dtype, lambda a, ww, bb: a @ ww.T + (0 if bb is None else bb), "matmul + bias")
    # Does it depend on the row count? Halve until clean, then report the smallest dirty block.
    print("fp16 F.linear by row block (first block only):")
    n = x.shape[0]
    while n >= 1024:
        xs = x[:n].to(torch.float16)
        bad = int((~torch.isfinite(F.linear(xs, w.to(torch.float16), None if b is None else b.to(torch.float16)))).sum().item())
        print(f"  rows {n:>10}: non-finite {bad}", flush=True)
        if bad == 0:
            break
        n //= 2
    print("fp16 F.linear over consecutive 1M-row slices (which region is dirty):")
    step = 1 << 20
    for s in range(0, x.shape[0], step):
        xs = x[s:s + step].to(torch.float16)
        bad = int((~torch.isfinite(F.linear(xs, w.to(torch.float16), None if b is None else b.to(torch.float16)))).sum().item())
        if bad:
            print(f"  rows {s}..{s + xs.shape[0]}: non-finite {bad}", flush=True)
    print("CPU fp32 reference of the same matmul: non-finite",
          int((~torch.isfinite(F.linear(x.cpu().float(), w.cpu().float(), None if b is None else b.cpu().float()))).sum().item()))
