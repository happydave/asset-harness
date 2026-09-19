"""Run the TRELLIS.2 geometry path from the shipped template, on one image.

Node ids mirror the template's (3d_pixal3d_trellis2_image_to_model.json) so the wiring can be
diffed against it. The Trellis2 arm is taken directly (ComfySwitchNode switch=True), with the
frontend-only pass-throughs (Preview/MaskPreview/switch nodes) resolved to their sources.
"""
import json, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:7121"
image = sys.argv[1] if len(sys.argv) > 1 else "prop_crate.png"
seed_ss = int(sys.argv[2]) if len(sys.argv) > 2 else 56
prefix = sys.argv[3] if len(sys.argv) > 3 else "3d/wi1600_trellis2"
unet  = sys.argv[4] if len(sys.argv) > 4 else "trellis_2_int8_convrot.safetensors"

G = {
  "122": {"class_type": "LoadImage", "inputs": {"image": image}},
  "193": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}},
  "192": {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": ["193", 0], "image": ["122", 0]}},
  "312": {"class_type": "ImageCropToMask", "inputs": {
      "images": ["122", 0], "masks": ["192", 0],
      "width": 1024, "height": 1024, "pad_factor": 1.1, "grow_mask": 0, "background": "#000000"}},
  "15":  {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "dino_v3_L_naf_fp32.safetensors"}},
  "299": {"class_type": "Trellis2Conditioning", "inputs": {"clip_vision_model": ["15", 0], "image": ["312", 0]}},

  "40":  {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
  "199": {"class_type": "CFGOverride", "inputs": {"model": ["40", 0], "cfg": 1, "start_percent": 0.667, "end_percent": 1}},
  "125": {"class_type": "RescaleCFG", "inputs": {"model": ["199", 0], "multiplier": 0.7}},
  "108": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["125", 0], "shift": 5}},
  "279": {"class_type": "CFGOverride", "inputs": {"model": ["40", 0], "cfg": 1, "start_percent": 0.769, "end_percent": 1}},
  "126": {"class_type": "RescaleCFG", "inputs": {"model": ["279", 0], "multiplier": 0.5}},

  "117": {"class_type": "VAELoader", "inputs": {"vae_name": "trellis_2_shape_vae_bf16.safetensors"}},
  "87":  {"class_type": "EmptyTrellis2LatentStructure", "inputs": {"batch_size": 1}},

  "3":   {"class_type": "KSampler", "inputs": {"model": ["108", 0], "seed": seed_ss, "steps": 12, "cfg": 7.5,
          "sampler_name": "euler", "scheduler": "normal", "positive": ["299", 0], "negative": ["299", 1],
          "latent_image": ["87", 0], "denoise": 1}},
  "119": {"class_type": "VaeDecodeStructureTrellis2", "inputs": {"samples": ["3", 0], "vae": ["117", 0], "resolution": "32"}},
  "91":  {"class_type": "Trellis2ShapeStage", "inputs": {"positive": ["299", 0], "negative": ["299", 1], "voxel": ["119", 0]}},
  "18":  {"class_type": "KSampler", "inputs": {"model": ["126", 0], "seed": 42, "steps": 20, "cfg": 7.5,
          "sampler_name": "euler", "scheduler": "normal", "positive": ["91", 0], "negative": ["91", 1],
          "latent_image": ["91", 2], "denoise": 1}},
  "94":  {"class_type": "Trellis2UpsampleStage", "inputs": {"positive": ["91", 0], "negative": ["91", 1],
          "shape_latent": ["18", 0], "vae": ["117", 0], "target_resolution": 1536}},
  "23":  {"class_type": "KSampler", "inputs": {"model": ["126", 0], "seed": 42, "steps": 12, "cfg": 7.5,
          "sampler_name": "euler", "scheduler": "simple", "positive": ["94", 0], "negative": ["94", 1],
          "latent_image": ["94", 2], "denoise": 1}},
  "92":  {"class_type": "VaeDecodeShapeTrellis", "inputs": {"samples": ["23", 0], "vae": ["117", 0]}},
  "202": {"class_type": "GetMeshInfo", "inputs": {"mesh": ["92", 0]}},
  "285": {"class_type": "MeshToFile3D", "inputs": {"mesh": ["202", 0]}},
  "322": {"class_type": "Save3DAdvanced", "inputs": {"model_3d": ["285", 0], "filename_prefix": prefix,
          "viewport_state": "", "width": 1024, "height": 1024}},
}

req = urllib.request.Request(f"{BASE}/prompt", method="POST",
        data=json.dumps({"prompt": G, "client_id": "wi1600"}).encode(),
        headers={"Content-Type": "application/json"})
try:
    resp = json.load(urllib.request.urlopen(req, timeout=60))
except urllib.error.HTTPError as e:
    print("VALIDATION FAILED:", json.dumps(json.loads(e.read().decode()), indent=2)[:4000])
    raise SystemExit(2)

pid = resp["prompt_id"]
print("PROMPT_ID", pid, flush=True)
t0 = time.time()
while True:
    time.sleep(10)
    h = json.load(urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=30))
    if pid in h:
        st = h[pid]["status"]
        print(f"DONE status={st.get('status_str')} completed={st.get('completed')} elapsed={time.time()-t0:.0f}s", flush=True)
        print("OUTPUTS", json.dumps(h[pid].get("outputs", {}))[:3000], flush=True)
        for m in st.get("messages", [])[-8:]:
            print("MSG", json.dumps(m)[:600], flush=True)
        break
    if time.time() - t0 > 5400:
        print("TIMEOUT after 90min", flush=True); break
