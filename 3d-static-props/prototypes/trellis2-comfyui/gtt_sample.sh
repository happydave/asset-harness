#!/bin/bash
# Memory and busy sampler for a unified-memory APU (gtr, gfx1151), where the GPU allocates system RAM
# through GTT and rocm-smi's VRAM figure covers only the small carve-out. One TSV row per interval:
# GTT used, carve-out used, MemAvailable, GPU busy, the RSS of one container's main process, and the
# epoch time (for aligning with records stamped in epoch seconds). ts carries milliseconds.
#   gtt_sample.sh OUT.tsv [CONTAINER] [INTERVAL_S]      stop with kill / Ctrl-C
set -u
out=${1:?output tsv}
ctr=${2:-}
interval=${3:-1}

dev=""
for d in /sys/class/drm/card*/device; do
  [ -r "$d/mem_info_gtt_used" ] && { dev=$d; break; }
done
[ -n "$dev" ] || { echo "no amdgpu device with mem_info_gtt_used" >&2; exit 2; }

pid=""
if [ -n "$ctr" ]; then
  pid=$(podman inspect --format '{{.State.Pid}}' "$ctr" 2>/dev/null) || pid=""
  [ -n "$pid" ] && [ "$pid" != 0 ] || { echo "container $ctr has no running process" >&2; exit 2; }
fi

mib() { echo $(( $1 / 1048576 )); }
echo -e "ts\tgtt_used_mib\tvram_used_mib\tmem_available_mib\tgpu_busy_pct\tctr_rss_mib\tepoch_s" > "$out"
while true; do
  gtt=$(cat "$dev/mem_info_gtt_used")
  vram=$(cat "$dev/mem_info_vram_used")
  avail=$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
  busy=$(cat "$dev/gpu_busy_percent" 2>/dev/null || echo NA)
  rss=NA
  if [ -n "$pid" ]; then
    rss=$(awk '/^VmRSS:/ {print int($2 / 1024)}' "/proc/$pid/status" 2>/dev/null || echo gone)
  fi
  now=$(date +%s.%3N)
  echo -e "$(date -d "@$now" +%H:%M:%S.%3N)\t$(mib "$gtt")\t$(mib "$vram")\t$(mib "$avail")\t${busy}\t${rss}\t${now}" >> "$out"
  sleep "$interval"
done
