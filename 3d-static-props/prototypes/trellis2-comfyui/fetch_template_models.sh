#!/bin/bash
# Fetch the three models the shipped TRELLIS.2 template needs beyond the geometry lane, into
# ~/wi1745/models at the repos' paths; each file is kept only if its size matches the HF tree API.
set -u
W=$HOME/wi1745/models
get() { local repo=$1 path=$2 size=$3
  curl -fsSL --retry 3 -o "$W/$path.part" "https://huggingface.co/$repo/resolve/main/$path" || { echo "FAIL $path"; return 1; }
  got=$(stat -c %s "$W/$path.part")
  if [ "$got" = "$size" ]; then mv "$W/$path.part" "$W/$path"; echo "OK $path $got"; else echo "SIZE MISMATCH $path got $got want $size"; rm -f "$W/$path.part"; fi; }
sizes=$(curl -fsS "https://huggingface.co/api/models/Comfy-Org/TRELLIS.2/tree/main/vae"; echo; curl -fsS "https://huggingface.co/api/models/Comfy-Org/Pixal3D/tree/main/diffusion_models"; echo; curl -fsS "https://huggingface.co/api/models/Comfy-Org/MoGe/tree/main/geometry_estimation")
sz() { printf '%s' "$sizes" | python3 -c "import sys,json
for line in sys.stdin.read().splitlines():
  if line.strip():
    for x in json.loads(line):
      if x['path']=='$1': print(x['size'])"; }
get Comfy-Org/TRELLIS.2 vae/trellis_2_texture_vae_bf16.safetensors $(sz vae/trellis_2_texture_vae_bf16.safetensors)
get Comfy-Org/MoGe geometry_estimation/moge_2_vitl_normal_fp16.safetensors $(sz geometry_estimation/moge_2_vitl_normal_fp16.safetensors)
get Comfy-Org/Pixal3D diffusion_models/pixal3d_int8_convrot.safetensors $(sz diffusion_models/pixal3d_int8_convrot.safetensors)
echo FETCH-DONE
