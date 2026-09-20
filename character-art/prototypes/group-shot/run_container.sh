#!/usr/bin/env bash
# Bring up the WI 1626 ComfyUI container on ai2, as notdave, rootless podman.
#
# Reuses WI 1611's image unchanged -- the group-shot spike needs the same core 0.34.6 stack plus
# that work item's masters and mattes, so rebuilding would cost 31 GB to arrive at the same place.
# Run flags are WI 1064's, carried through WIs 1600/1611: they are what makes ROCm work here.
set -u

NAME=wi1626
PORT=7126
IMAGE=localhost/wi1611-comfyui:0.34.6
SRC=$HOME/wi1611/ComfyUI          # ComfyUI checkout + custom nodes, shared with WI 1611
M=$HOME/wi1611/models             # detectors, upscaler, birefnet
W=$HOME/wi1626                    # this spike's own input/output/controlnet

podman rm -f "$NAME" >/dev/null 2>&1

podman run -d --name "$NAME" \
  --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
  -e ROCR_VISIBLE_DEVICES=0 -e HSA_ENABLE_SDMA=0 \
  -p "127.0.0.1:${PORT}:8188" \
  -v "$SRC:/opt/comfyui" \
  -v /opt/comfyui/models/checkpoints:/opt/comfyui/models/checkpoints:ro \
  -v "$M/upscale_models:/opt/comfyui/models/upscale_models" \
  -v "$M/ultralytics:/opt/comfyui/models/ultralytics" \
  -v "$M/background_removal:/opt/comfyui/models/background_removal" \
  -v "$W/controlnet:/opt/comfyui/models/controlnet" \
  -v "$W/input:/opt/comfyui/input" \
  -v "$W/output:/opt/comfyui/output" \
  "$IMAGE" \
  python main.py --listen 0.0.0.0 --port 8188 --disable-mmap
  # --listen 0.0.0.0 binds inside the container; the publish keeps it loopback-only on ai2.
  # --disable-mmap is a host fragility (WI 1054), not a preference.
