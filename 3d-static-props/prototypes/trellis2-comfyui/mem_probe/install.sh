#!/usr/bin/env bash
# Install the memory probe into a ComfyUI checkout's custom_nodes/ (the checkout the container
# mounts at /opt/comfyui). Idempotent. Inert unless MEM_PROBE_DIR is set in the server's environment.
#   ./install.sh /path/to/ComfyUI
set -eu
CHECKOUT=${1:?usage: install.sh <ComfyUI checkout>}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$CHECKOUT/custom_nodes/mem_probe"
cp "$HERE/__init__.py" "$CHECKOUT/custom_nodes/mem_probe/__init__.py"
echo "mem_probe installed in $CHECKOUT/custom_nodes/mem_probe (restart ComfyUI to load it)"
