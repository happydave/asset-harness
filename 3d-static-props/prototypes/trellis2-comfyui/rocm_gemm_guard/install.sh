#!/usr/bin/env bash
# Install the ROCm GEMM guard into a ComfyUI checkout's custom_nodes/ (the checkout the container
# mounts at /opt/comfyui). Idempotent; re-run after updating the guard.
#   ./install.sh /path/to/ComfyUI
set -eu
CHECKOUT=${1:?usage: install.sh <ComfyUI checkout>}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$CHECKOUT/custom_nodes/rocm_gemm_guard"
cp "$HERE/__init__.py" "$CHECKOUT/custom_nodes/rocm_gemm_guard/__init__.py"
echo "rocm_gemm_guard installed in $CHECKOUT/custom_nodes/rocm_gemm_guard (restart ComfyUI to load it)"
