"""Synthetic version of the WI 1613 reproducer: random fp16 [M, 128] @ [8, 128]^T on the GPU against
the CPU fp32 result, over row counts around 2^20, plus a few N and K variants. No model, no file."""
import sys, torch, torch.nn.functional as F
torch.manual_seed(0)
dev = "cuda"
print(torch.__version__, torch.version.hip or torch.version.cuda, torch.cuda.get_device_name(0), flush=True)
def trial(M, N=8, K=128, dtype=torch.float16, scale=8.0):
    x = (torch.randn(M, K) * scale).to(dtype)
    w = (torch.randn(N, K) * 0.5).to(dtype)
    b = torch.zeros(N, dtype=dtype)
    ref = F.linear(x.float(), w.float(), b.float())
    out = F.linear(x.to(dev), w.to(dev), b.to(dev)).float().cpu()
    torch.cuda.synchronize()
    fin = torch.isfinite(out)
    bad = int((~fin).sum()); dev_max = float((out[fin] - ref[fin]).abs().max()) if fin.any() else float("nan")
    wrong = int(((out[fin] - ref[fin]).abs() > 1.0).sum())
    return bad, wrong, dev_max
for M in (1 << 20, (1 << 20) + 1, 1_200_000, 1_400_000, 1_577_827, 2_000_000, 3_000_000):
    bad, wrong, d = trial(M)
    print(f"fp16 M={M:>9} N=8 K=128: non-finite {bad:>8} |dev|>1 {wrong:>9} max|dev| {d:.2f}", flush=True)
for N, K in ((16, 128), (64, 128), (8, 256), (8, 64), (128, 128)):
    bad, wrong, d = trial(1_577_827, N, K)
    print(f"fp16 M=1577827 N={N} K={K}: non-finite {bad:>8} |dev|>1 {wrong:>9} max|dev| {d:.2f}", flush=True)
for dtype in (torch.bfloat16, torch.float32):
    bad, wrong, d = trial(1_577_827, dtype=dtype)
    print(f"{str(dtype):<14} M=1577827 N=8 K=128: non-finite {bad:>8} |dev|>1 {wrong:>9} max|dev| {d:.2f}", flush=True)
