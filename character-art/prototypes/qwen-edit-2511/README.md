# Qwen-Image-Edit-2511 re-projection on gfx1201

Scaffolding from the WI 1599 spike: does the edit model preserve non-human race features (horns,
snouts, tusks) when it re-projects a character to a new angle? Short answer: **yes — nothing was
humanised in any of 11 runs.** Full evidence and verdict:
`tickets/docs/pending/1599-ah-spike-edit-model-non-human-faces/spike.md`.

Nothing here is production code. It is the smallest thing that produced a decisive result, kept
because WI 1611's harness will need the same graph.

## The image

**Reuses WI 1600's container unchanged** — `localhost/wi1600-comfyui:0.34.6` on the digest-pinned
`docker.io/rocm/pytorch@sha256:4449f856…83179e`. No new image was built. See
`../../../3d-static-props/prototypes/trellis2-comfyui/` for the Containerfile. Run flags are the
same, with a different port and this spike's own model/input/output mounts:

```
podman run -d --name wi1599 \
  --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
  -e ROCR_VISIBLE_DEVICES=0 -e HSA_ENABLE_SDMA=0 \
  -p 127.0.0.1:7122:7122 \
  -v $HOME/wi1600/ComfyUI:/opt/comfyui:z -v $HOME/wi1599/models:/opt/comfyui/models:z \
  -v $HOME/wi1599/input:/opt/comfyui/input:z -v $HOME/wi1599/output:/opt/comfyui/output:z \
  localhost/wi1600-comfyui:0.34.6 \
  python main.py --listen 0.0.0.0 --port 7122 --disable-mmap
```

## Models — all apache-2.0 (`fetch.sh` gets them)

| File | Repo | Size |
|---|---|---|
| `diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors` | `Comfy-Org/Qwen-Image-Edit_ComfyUI` | 19,549 MiB |
| `text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` | `Comfy-Org/Qwen-Image_ComfyUI` | 8,949 MiB |
| `vae/qwen_image_vae.safetensors` | `Comfy-Org/Qwen-Image_ComfyUI` | 242 MiB |
| `loras/character_turnaround_sheet_v3_…_000000400.safetensors` | `tarn59/character_turnaround_sheet_qwen_edit_2511` | 281 MiB |

**There is no `qwen_image_edit_2511_fp8_e4m3fn`** — that exists for 2509 only. 2511's in-core
quantised options are `int8_convrot` and `fp8mixed`. `int8_convrot` is the one with a measured
native `comfy-kitchen` HIP kernel on gfx1201 (WI 1600).

## Scripts

- `fetch.sh` — the four weights, resumable.
- `gen_portraits.py` / `gen_dragonborn2.py` — generate candidate source portraits on an SDXL
  booru-tag checkpoint. Full-figure at the LoRA's 600×1080 aspect, **cropped not squeezed**.
- `run_arm_a.py SUBJECT MODE SEED [--no-lora]` — the re-projection. Modes: `turnaround`
  (2600×1080, trigger prompt, with LoRA), `reangle` (600×1080 back view), `profile` (600×1080 side).
- `measure_narrowing.py` — subject width/height, source vs output, with the human as reference.
  **Known flaw: unreliable for tailed subjects** — the bounding box includes a tail whose position
  moves between source and output. Segment the head if you need this for a tailed character.

## Traps this spike hit

- **The LoRA has a trigger phrase**, `Character turnaround sheet`. Without it the LoRA is inert and
  a LoRA-present run looks exactly like a LoRA-absent one.
- **The LoRA narrows characters ~10 % even after its card's prescribed +20 % horizontal fix**;
  ~+33 % is closer. **Base 2511 re-pose does not narrow at all** and needs no correction.
- **Budget sheet width per panel, not per sheet.** A 2600 px five-view sheet gives each view 520 px,
  and that — not the model — is what softens fine detail like teeth and scale texture.
- **VRAM: 32,509 MiB of 32,624 at 2600×1080.** 115 MiB spare. No batch of two on this card.
- **Don't guess sampler settings** — `image_qwen_image_edit_2511_int8.json` in
  `Comfy-Org/workflow_templates` is the template for this exact model file, and it also shows a
  `LoraLoaderModelOnly` on the int8 UNet, which is how we knew LoRA-over-int8 was supported.
