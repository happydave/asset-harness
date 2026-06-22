#!/usr/bin/env python3
"""TripoSR (MIT) image-to-3D test: single image -> mesh -> glTF (.glb).

Clean-lane candidate (MIT incl. weights). Graph: TripoSRModelLoader -> TripoSRSampler -> SaveGLB
(Flowty `ComfyUI-Flowty-TripoSR` nodes). Reuses the HTTP helpers from run_hunyuan3d.py.
"""
import argparse
from pathlib import Path

from run_hunyuan3d import download, queue, upload_image, wait


def build_graph(image_name: str, model: str, geom_res: int, threshold: float, prefix: str) -> dict:
    return {
        "1": {"class_type": "TripoSRModelLoader", "inputs": {"model": model, "chunk_size": 8192}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "TripoSRSampler",
              "inputs": {"model": ["1", 0], "reference_image": ["2", 0],
                         "geometry_resolution": geom_res, "threshold": threshold}},
        "4": {"class_type": "SaveGLB", "inputs": {"mesh": ["3", 0], "filename_prefix": prefix}},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", default="ilustmix_v9.safetensors",
                    help="TripoSRModelLoader combo value (Flowty may auto-download TripoSR regardless)")
    ap.add_argument("--geom-res", type=int, default=256)
    ap.add_argument("--threshold", type=float, default=25.0)
    ap.add_argument("--name", default="triposr")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    server = args.server.rstrip("/")
    name = upload_image(server, Path(args.image))
    graph = build_graph(name, args.model, args.geom_res, args.threshold, f"asset_harness/{args.name}")
    print(f"queueing TripoSR for {name} ...")
    pid = queue(server, graph)
    print(f"prompt_id={pid}; waiting ...")
    hist = wait(server, pid)
    print("status:", hist.get("status", {}).get("status_str"))
    saved = download(server, hist, Path(args.out))
    print(f"downloaded {len(saved)} file(s): {[p.name for p in saved]}")
    if not saved:
        # surface any execution error recorded in history
        st = hist.get("status", {})
        print("messages:", st.get("messages"))


if __name__ == "__main__":
    main()
