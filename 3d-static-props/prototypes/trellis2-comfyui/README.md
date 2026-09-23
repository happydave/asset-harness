# TRELLIS.2 via ComfyUI core nodes, on gfx1201

Scaffolding from the WI 1600 spike: does ComfyUI 0.34.x's **core** TRELLIS.2 path run on the
32 GiB R9700 (gfx1201) in `ai2`? Short answer: yes, natively, ~270 s per object — but the shipped
template's own `RemeshMesh` step dies on NaN vertices the decode emits. Full findings and evidence:
`tickets/docs/pending/1600-ah-spike-trellis2-comfyui-core-rocm/spike.md`.

Nothing here is production code. It is the smallest thing that produced a decisive result, kept
because the image recipe is the uncertain half of any future containerised ComfyUI worker.

## The image

`Containerfile` builds on the digest-pinned ROCm base WI 1064/1065 proved on this box:
`docker.io/rocm/pytorch@sha256:4449f856…83179e` (ROCm 7.2.4 matching the host, torch 2.10.0, py 3.12).
ComfyUI's source, models, input and output are **runtime bind mounts** — the image pins the stack only.

`check_torch.py` runs as a build step and is the load-bearing assertion: ComfyUI's `requirements.txt`
lists `torch`/`torchvision`/`torchaudio` unpinned, so the build fails loudly if pip ever replaces the
base's ROCm wheels with CUDA ones instead of silently producing a CPU-bound box.

Build and run, as `notdave` on `ai2`:

```
podman build -t localhost/wi1600-comfyui:0.34.6 -f Containerfile .
podman run -d --name wi1600 \
  --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
  -e ROCR_VISIBLE_DEVICES=0 -e HSA_ENABLE_SDMA=0 \
  -p 127.0.0.1:7121:7121 \
  -v $PWD/ComfyUI:/opt/comfyui:z -v $PWD/models:/opt/comfyui/models:z \
  -v $PWD/input:/opt/comfyui/input:z -v $PWD/output:/opt/comfyui/output:z \
  localhost/wi1600-comfyui:0.34.6 \
  python main.py --listen 0.0.0.0 --port 7121 --disable-mmap
```

`--listen 0.0.0.0` is inside the container; the host-side publish keeps it on loopback. `--listen
127.0.0.1` binds the container's own loopback and is unreachable through the published port.
`--disable-mmap` is an `ai2` host requirement (WI 1054) and applies in a container too.
`ROCR_VISIBLE_DEVICES=0` selects the R9700 over the iGPU.

## Models

Four MIT repos, ~16 GiB for the int8 path, into the bind-mounted `models/` at the paths the repos
already use (`diffusion_models/`, `vae/`, `clip_vision/`, `background_removal/`,
`geometry_estimation/`):

| File | Repo |
|---|---|
| `diffusion_models/trellis_2_int8_convrot.safetensors` (5.0 GiB) | `Comfy-Org/TRELLIS.2` |
| `diffusion_models/trellis_2_bf16.safetensors` (9.6 GiB, alternative) | `Comfy-Org/TRELLIS.2` |
| `vae/trellis_2_shape_vae_bf16.safetensors` | `Comfy-Org/TRELLIS.2` |
| `vae/trellis_2_texture_vae_bf16.safetensors` | `Comfy-Org/TRELLIS.2` |
| `clip_vision/dino_v3_L_naf_fp32.safetensors` | `Comfy-Org/Pixal3D` — **not** the TRELLIS.2 repo |
| `background_removal/birefnet.safetensors` | `Comfy-Org/BiRefNet` |
| `geometry_estimation/moge_2_vitl_normal_fp16.safetensors` | `Comfy-Org/MoGe` |
| `diffusion_models/pixal3d_int8_convrot.safetensors` (second arm) | `Comfy-Org/Pixal3D` |

## Scripts

- `run_trellis2.py IMAGE SEED PREFIX [UNET]` — the shipped template's geometry path in API format,
  node ids matching `3d_pixal3d_trellis2_image_to_model.json` so it can be diffed against upstream.
- `run_trellis2_full.py` — the same plus the stock postprocess tail. **Currently fails** at
  `RemeshMesh`; kept because that failure is the finding.
- `glb_probe.py FILE` — NaN/inf census of a GLB's JSON chunk and vertex buffers.
- `glb_repair.py IN OUT` — drop non-finite vertices and any face touching one. Needed before Blender
  will open the raw output at all.
- `render_glb.py` (via `blender -b -P`) — four-angle render plus mesh stats, for looking at the
  artifact with something other than the stack that made it.
- `gpu_sample.sh [OUT]` — `rocm-smi` busy/VRAM sampling, to tell real GPU work from a CPU fallback.
- `schema_dump.py [BASE]` — dump the node schemas this graph depends on from a running server.

WI 1613 (the NaN root cause) added:

- `run_trellis2_decode.py IMAGE DECODE PREFIX [BASE] [SEED_SS] [SEED_SHAPE]` — the geometry path at a
  chosen decode resolution (512 = the shape latent decoded directly, else an upsample target ≥ 1024),
  with the GLB census inline (pure-Python fallback when the host has no numpy).
- `wi1613_latent_io/` — a throwaway custom node pair, `SaveTrellisLatent` / `LoadTrellisLatent`, that
  saves a TRELLIS latent dict whole (`coords`, `coord_counts`, `coord_resolution` included — core
  `SaveLatent` drops them). Copy into `custom_nodes/` of the checkout the container mounts.
- `trellis2_latent_io.py save|decode` — save the latent the decode consumes, or decode a saved one
  (decode-only: ~8.5 GiB, no diffusion model resident), so one latent can be decoded on two vendors.
  `LoadTrellisLatent` keys ComfyUI's cache on the file's mtime: `touch` the file for a real re-decode.
- `bisect_decode.py LATENT [RUNS] [--cpu]` — the decode under forward hooks on every decoder module,
  naming the first one whose output is non-finite. Runs inside the container (`podman exec -w
  /opt/comfyui …`). Must run under `torch.inference_mode` (it does): outside it the autograd graph
  fills the card.
- `repro_linear.py LATENT [REPEATS]` — captures the input to `blocks.3.4.to_subdiv` during one real
  decode, saves it, and re-runs that one matmul in fp16 / bf16 / fp32, by row block and by slice.

## Gotchas

- **`COMFY_DYNAMICCOMBO_V3` inputs are flattened with dotted keys over the API**, not nested:
  `"sign_mode": "udf"` *plus* `"sign_mode.qef": false`. The validator names them `sign_mode.qef`.
- **ComfyUI caches the whole graph**, so resubmitting identical inputs returns the first run's result
  in seconds with every node listed in `execution_cached`. Restart the container for a cold run.
- **`--cpu-vae` does not work with these nodes** — the sparse conv3d gets weights on CPU and
  activations on CUDA and raises.
