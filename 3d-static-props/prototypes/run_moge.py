#!/usr/bin/env python3
"""MoGe (MIT) monocular-geometry test: single image -> 2.5D relief mesh -> glTF (.glb).

Already installed on ai2. Graph: LoadMoGeModel -> MoGeInference -> MoGePointMapToMesh -> SaveGLB.
Single-view (camera-facing) geometry — good for terrain/backdrops, not closed objects. Reuses the
HTTP helpers from run_hunyuan3d.py.
"""
import argparse
from pathlib import Path

from run_hunyuan3d import download, queue, upload_image, wait

MODEL = "moge_2_vitl_normal_fp16.safetensors"


def build_graph(image_name: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadMoGeModel", "inputs": {"model_name": MODEL}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "MoGeInference",
              "inputs": {"moge_model": ["1", 0], "image": ["2", 0], "resolution_level": 9,
                         "fov_x_degrees": 0.0, "batch_size": 4, "force_projection": True,
                         "apply_mask": True}},
        "4": {"class_type": "MoGePointMapToMesh",
              "inputs": {"moge_geometry": ["3", 0], "batch_index": 0, "decimation": 1,
                         "discontinuity_threshold": 0.04, "texture": True}},
        "5": {"class_type": "SaveGLB", "inputs": {"mesh": ["4", 0], "filename_prefix": prefix}},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True)
    ap.add_argument("--name", default="moge")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    server = args.server.rstrip("/")
    name = upload_image(server, Path(args.image))
    graph = build_graph(name, f"asset_harness/{args.name}")
    print(f"queueing MoGe for {name} ...")
    pid = queue(server, graph)
    print(f"prompt_id={pid}; waiting ...")
    hist = wait(server, pid)
    print("status:", hist.get("status", {}).get("status_str"))
    saved = download(server, hist, Path(args.out))
    print(f"downloaded {len(saved)} file(s): {[p.name for p in saved]}")
    if not saved:
        print("messages:", hist.get("status", {}).get("messages"))


if __name__ == "__main__":
    main()
