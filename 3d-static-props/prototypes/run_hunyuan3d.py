#!/usr/bin/env python3
"""Asset-harness 3D static-prop prototype: single image -> Hunyuan3D 2.0 -> glTF (.glb).

Mirrors ComfyUI's native `3d_hunyuan3d_image_to_model` template (the local, open path):
  ImageOnlyCheckpointLoader -> CLIPVisionEncode -> Hunyuan3Dv2Conditioning
  -> KSampler -> VAEDecodeHunyuan3D -> VoxelToMesh -> SaveGLB

Bevy loads the resulting .glb natively. NOTE: the mesh is produced by Hunyuan3D 2.0, which is
under the **Tencent Hunyuan Community License** (NOT Apache) — see discover.md before shipping.

Requires `hunyuan3d-dit-v2_fp16.safetensors` in ComfyUI/models/checkpoints/ (bundles
MODEL+CLIP_VISION+VAE). Stdlib + requests only.
"""
import argparse
import time
import uuid
from pathlib import Path

import requests

CKPT = "hunyuan3d-dit-v2_fp16.safetensors"


def build_graph(image_name: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "CLIPVisionEncode",
              "inputs": {"clip_vision": ["1", 1], "image": ["2", 0], "crop": "none"}},
        "4": {"class_type": "Hunyuan3Dv2Conditioning", "inputs": {"clip_vision_output": ["3", 0]}},
        "5": {"class_type": "EmptyLatentHunyuan3Dv2", "inputs": {"resolution": 3072, "batch_size": 1}},
        "6": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["6", 0], "seed": seed, "steps": 20, "cfg": 8.0,
                         "sampler_name": "euler", "scheduler": "normal",
                         "positive": ["4", 0], "negative": ["4", 1],
                         "latent_image": ["5", 0], "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeHunyuan3D",
              "inputs": {"samples": ["7", 0], "vae": ["1", 2], "num_chunks": 8000, "octree_resolution": 256}},
        "9": {"class_type": "VoxelToMesh",
              "inputs": {"voxel": ["8", 0], "algorithm": "surface net", "threshold": 0.6}},
        "10": {"class_type": "SaveGLB", "inputs": {"mesh": ["9", 0], "filename_prefix": prefix}},
    }


def upload_image(server, path: Path) -> str:
    with path.open("rb") as f:
        r = requests.post(f"{server}/upload/image",
                          files={"image": (path.name, f, "image/png")},
                          data={"overwrite": "true"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]


def queue(server, graph) -> str:
    r = requests.post(f"{server}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def wait(server, pid, timeout=1800) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"{server}/history/{pid}", timeout=30).json()
        if pid in h:
            return h[pid]
        time.sleep(3)
    raise SystemExit("timed out waiting for Hunyuan3D")


def download(server, hist, out_dir: Path) -> list[Path]:
    """SaveGLB reports its file under some output key; scan generically for filename dicts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for entries in node_out.values():
            if not isinstance(entries, list):
                continue
            for e in entries:
                if isinstance(e, dict) and e.get("filename"):
                    r = requests.get(f"{server}/view", params={
                        "filename": e["filename"], "subfolder": e.get("subfolder", ""),
                        "type": e.get("type", "output")}, timeout=120)
                    if r.ok and r.content:
                        p = out_dir / e["filename"]
                        p.write_bytes(r.content)
                        saved.append(p)
    return saved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True, help="concept image (single object, plain background)")
    ap.add_argument("--name", default="prop")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args()
    server = args.server.rstrip("/")
    name = upload_image(server, Path(args.image))
    graph = build_graph(name, args.seed, f"asset_harness/{args.name}")
    print(f"queueing Hunyuan3D for {name} ...")
    pid = queue(server, graph)
    print(f"prompt_id={pid}; waiting (image-to-3D is slow) ...")
    hist = wait(server, pid)
    print("status:", hist.get("status", {}).get("status_str"))
    saved = download(server, hist, Path(args.out))
    print(f"downloaded {len(saved)} file(s):")
    for p in saved:
        print("  ", p)
    if not saved:
        print("  (no files — check that the Hunyuan3D model is installed and the run succeeded)")


if __name__ == "__main__":
    main()
