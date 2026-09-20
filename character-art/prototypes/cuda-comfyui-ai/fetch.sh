#!/bin/bash
# WI 1616 arm C weights. Q3_K_M is the only GGUF that fits the 12 GiB card with room to work.
set -u
cd ~/wi1616/models
get () { echo "--- $2"; curl -L -C - --retry 5 --retry-delay 5 --fail -sS -o "$2" "$1" || echo "FAILED $2"; }
get "https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q3_K_M.gguf" \
    diffusion_models/qwen-image-edit-2511-Q3_K_M.gguf
get "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
get "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
    vae/qwen_image_vae.safetensors
get "https://huggingface.co/tarn59/character_turnaround_sheet_qwen_edit_2511/resolve/main/character_turnaround_sheet_v3_qwen_image_edit_2511_000000400.safetensors" \
    loras/character_turnaround_sheet_v3_qwen_image_edit_2511_000000400.safetensors
echo "=== sizes ==="; find . -type f \( -name '*.gguf' -o -name '*.safetensors' \) -printf '%10s  %p\n'
echo "=== done ==="
