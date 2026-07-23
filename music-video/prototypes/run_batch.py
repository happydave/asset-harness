#!/usr/bin/env python3
"""Run a batch of Wan i2v clips SEQUENTIALLY, each keyed on the server's job state — never on `pgrep`.

This is the pattern that would have prevented the WI 1018 overnight wedge: submit one clip, wait on its
`/history` terminal state, download it, check the result, THEN move to the next. One clip's failure is
caught and the batch continues; nothing depends on a client process staying alive, and no wall-clock cap
discards a finished clip.

Spec: a JSON file containing a list of clip objects. Only `image`, `prompt`, `out` are required:
  [
    {"image": "in/a.png", "prompt": "...", "out": "out/a", "no_lora": true},
    {"image": "in/b.png", "prompt": "...", "out": "out/b", "width": 1280, "height": 720, "seed": 7}
  ]
Optional per-clip keys (else the defaults below): no_lora, width(1280), height(720), frames(81),
fps(16), seed(901), steps, cfg, fp16.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import comfy_client
import generate_clip as gc


def _graph_for(server: str, spec: dict):
    use_lora = not spec.get("no_lora", False)
    steps = spec.get("steps", 4 if use_lora else 20)
    cfg = spec.get("cfg", 1.0 if use_lora else 3.5)
    fp16 = spec.get("fp16", False)
    high = gc.HIGH_UNET.replace("fp8_scaled", "fp16") if fp16 else gc.HIGH_UNET
    low = gc.LOW_UNET.replace("fp8_scaled", "fp16") if fp16 else gc.LOW_UNET
    image_name = gc.upload_image(server, Path(spec["image"]))
    return gc.build_graph(
        image_name, spec["prompt"],
        width=spec.get("width", 1280), height=spec.get("height", 720),
        frames=spec.get("frames", 81), fps=spec.get("fps", 16), seed=spec.get("seed", 901),
        use_lora=use_lora, steps=steps, cfg=cfg,
        prefix="asset_harness/mv_batch",
        high_unet=high, low_unet=low)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default=comfy_client.DEFAULT_SERVER)
    ap.add_argument("--spec", required=True, help="JSON file: list of clip specs")
    ap.add_argument("--backstop", type=float, default=None,
                    help="optional per-clip backstop seconds; default: wait indefinitely per clip")
    args = ap.parse_args()

    server = args.server.rstrip("/")
    specs = json.loads(Path(args.spec).read_text())
    print(f"batch of {len(specs)} clips against {server}")

    results = []
    for i, spec in enumerate(specs):
        out = spec.get("out", f"clip{i}")
        t0 = time.time()
        try:
            graph = _graph_for(server, spec)
            # queue -> wait on /history terminal state -> download. No pgrep, no discarding a finish.
            path = comfy_client.run_job(server, graph, out, kinds=("videos", "gifs"),
                                        backstop=args.backstop, label=f"{i+1}/{len(specs)}:{out}")[0]
            dt = time.time() - t0
            results.append((out, "ok", str(path), dt))
            print(f"[{i+1}/{len(specs)}] OK  {out} -> {path}  ({dt:.0f}s)")
        except Exception as e:
            # one clip's failure — of ANY kind (bad image, submit reject, server error, network) —
            # must not wedge the batch (the WI 1018 lesson). Catch broadly, record, keep going.
            dt = time.time() - t0
            results.append((out, "FAIL", f"{type(e).__name__}: {e}", dt))
            print(f"[{i+1}/{len(specs)}] FAIL {out}: {type(e).__name__}: {e}  ({dt:.0f}s) — continuing")

    ok = sum(1 for r in results if r[1] == "ok")
    print(f"\n=== batch done: {ok}/{len(results)} ok ===")
    for out, status, info, dt in results:
        print(f"  {status:4} {out}  {info}  ({dt:.0f}s)")
    if ok < len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
