#!/bin/bash
# Falsifiable check 1: was the GPU actually doing the work, or did it silently fall back to CPU?
# Samples every 5s: GPU busy %, VRAM used (MiB), and the container's CPU%.
out=${1:-~/wi1600/gpu_samples.tsv}
echo -e "ts\tgpu_busy_pct\tvram_used_mib\tsclk" > "$out"
while true; do
  u=$(rocm-smi --showuse 2>/dev/null | grep -oP 'GPU\[0\].*?GPU use \(%\): \K[0-9]+' | head -1)
  v=$(rocm-smi --showmeminfo vram 2>/dev/null | grep -oP 'GPU\[0\].*?VRAM Total Used Memory \(B\): \K[0-9]+' | head -1)
  s=$(rocm-smi --showclocks 2>/dev/null | grep -oP 'GPU\[0\].*?sclk clock speed:\s+\(\K[0-9]+' | head -1)
  echo -e "$(date +%H:%M:%S)\t${u:-NA}\t$(( ${v:-0} / 1048576 ))\t${s:-NA}" >> "$out"
  sleep 5
done
