#!/bin/bash
# WI 1599 arm A weights. Resumable; prints a size line per file at the end.
set -u
cd ~/wi1599/models
QIE=https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files
QI=https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files
LORA=https://huggingface.co/tarn59/character_turnaround_sheet_qwen_edit_2511/resolve/main
get () { # url dest
  echo "--- $2"
  curl -L -C - --retry 5 --retry-delay 5 --fail --silent --show-error -o "$2" "$1" || echo "FAILED $2"
}
get "$QIE/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors" diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors
get "$QI/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"             text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
get "$QI/vae/qwen_image_vae.safetensors"                                  vae/qwen_image_vae.safetensors
get "$LORA/character_turnaround_sheet_v3_qwen_image_edit_2511_000000400.safetensors" loras/character_turnaround_sheet_v3_qwen_image_edit_2511_000000400.safetensors
echo "=== sizes ==="
find . -name '*.safetensors' -printf '%10s  %p\n'
echo "=== done ==="
