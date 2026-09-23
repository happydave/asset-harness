#!/usr/bin/env python3
"""Hold a fixed amount of GPU memory until killed: a stand-in for another tenant's resident models
when measuring whether a run fits beside them (asset-harness WI 1766).

    python gtt_hog.py MIB

Allocates MIB mebibytes on the current device in 1 GiB tensors, writes to every page so the memory
is resident, prints `HELD <MIB>` and sleeps.
"""
import sys
import time

import torch

mib = int(sys.argv[1])
chunks = []
left = mib
while left > 0:
    n = min(left, 1024)
    t = torch.empty(n << 20, dtype=torch.uint8, device="cuda")
    t.fill_(1)
    chunks.append(t)
    left -= n
torch.cuda.synchronize()
print(f"HELD {mib} MiB in {len(chunks)} tensors; allocated {torch.cuda.memory_allocated() >> 20} MiB", flush=True)
while True:
    time.sleep(3600)
