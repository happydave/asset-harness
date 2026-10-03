#!/bin/bash
# WIs 2112 and 2120: the TRELLIS.2 template arm (v0.37.2, upsample target 1024) on each named input
# wi<WI>_<name>.png in input/, one at a time from a fresh server, then its licence sidecar. Skips a name
# whose glb already exists, so a stopped batch resumes. Stops before the next name when STOP exists.
#   gpu_pool.sh WI NAME...
set -u
WI=$1; shift
W=$HOME/wi1745; R=$W/results; NAME=wi1745; PORT=7121; IMG=localhost/wi1600-comfyui:0.37.2
serve() { local out=$1; podman rm -f $NAME >/dev/null 2>&1; mkdir -p $W/output/$out
  podman run -d --name $NAME --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
    -e HSA_ENABLE_SDMA=0 -e MEM_PROBE_DIR=/opt/comfyui/output/$out -p 127.0.0.1:$PORT:$PORT \
    -v $W/ComfyUI-0.37.2:/opt/comfyui -v $W/models:/opt/comfyui/models -v $W/input:/opt/comfyui/input -v $W/output:/opt/comfyui/output \
    $IMG python main.py --listen 0.0.0.0 --port $PORT >/dev/null
  until curl -fsS --max-time 3 http://127.0.0.1:$PORT/system_stats >/dev/null 2>&1; do sleep 3; done; }
graph() { python3 - "$1" "$2" "$WI" "$W" <<PY
import json, sys
src, name, wi, w = sys.argv[1:5]
h = json.load(open(src))
h["122"]["inputs"]["image"] = f"wi{wi}_{name}.png"
h["94"]["inputs"]["target_resolution"] = 1024
for v in h.values():
    p = v["inputs"].get("filename_prefix")
    if isinstance(p, str):
        v["inputs"]["filename_prefix"] = p.replace("3d/wi1751c_trellis2", f"3d/wi{wi}_{name}")
json.dump(h, open(f"{w}/lane/{wi}_{name}.json", "w"), indent=1)
PY
}
$W/lane/preflight.sh 40 || { echo "preflight refused"; exit 1; }
$W/lane/watchdog.sh 8 wi1745 $R/watchdog.log & WD=$!
trap "kill $WD 2>/dev/null; podman rm -f $NAME >/dev/null 2>&1" EXIT
for s in "$@"; do
  [ -e $W/lane/STOP_$WI ] && { echo "== stopped before $s $(date +%T)"; break; }
  ls $W/output/3d/wi${WI}_${s}_*.glb >/dev/null 2>&1 && { echo "== $s exists, skipped"; continue; }
  [ -e $W/input/wi${WI}_$s.png ] || { echo "no input for $s"; continue; }
  graph $W/lane/1751c_trellis2.json $s
  serve wi$WI/$s
  $W/lane/preflight.sh 40 | tail -1
  t=$(date +%s); echo "== ${WI}_$s $(date +%T)"
  python3 $W/lane/run_api_graph.py $W/lane/${WI}_$s.json http://127.0.0.1:$PORT 7200; echo "rc=$? in $(( $(date +%s) - t )) s"
  podman logs --timestamps $NAME > $R/${WI}_$s.server.log 2>&1
  f=$(ls -t $W/output/3d/wi${WI}_${s}_*.glb 2>/dev/null | head -1)
  if [ -n "$f" ]; then python3 $W/lane/lane_sidecar.py $f $W/lane/${WI}_$s.json --models $W/models --checkout $W/ComfyUI-0.37.2 --contracts $W/contracts; echo "sidecar $s rc=$?"; else echo "no glb for $s"; fi
done
echo "== done $(date +%T)"
