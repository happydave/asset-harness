#!/bin/bash
# WI 2112: the shape test set, the TRELLIS.2 template arm on ComfyUI v0.37.2 for each concept, one at a
# time, each from a fresh server, at an upsample target of 1024 (the template has 1536; the barrel did not
# leave the 1536 decode in 115 min, WI 2112); then the licence sidecar for each asset (gtr-trellis2-container
# runbook, steps 4, 6c, 7b and 8). From WI 1751's gpu_1751cd.sh.
set -u
W=$HOME/wi1745; R=$W/results; NAME=wi1745; PORT=7121; IMG=localhost/wi1600-comfyui:0.37.2
serve() { local out=$1; podman rm -f $NAME >/dev/null 2>&1; mkdir -p $W/output/$out
  podman run -d --name $NAME --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
    -e HSA_ENABLE_SDMA=0 -e MEM_PROBE_DIR=/opt/comfyui/output/$out -p 127.0.0.1:$PORT:$PORT \
    -v $W/ComfyUI-0.37.2:/opt/comfyui -v $W/models:/opt/comfyui/models -v $W/input:/opt/comfyui/input -v $W/output:/opt/comfyui/output \
    $IMG python main.py --listen 0.0.0.0 --port $PORT >/dev/null
  until curl -fsS --max-time 3 http://127.0.0.1:$PORT/system_stats >/dev/null 2>&1; do sleep 3; done
  podman logs $NAME 2>&1 | grep -E "rocm_(gemm|unwrap)_guard: |Device:" | cut -c1-160; }
arm() { local tag=$1
  $W/lane/preflight.sh 40 | tail -1
  $W/lane/gtt_sample.sh $R/$tag.tsv $NAME 0.1 & local SM=$!
  local t=$(date +%s); echo "== $tag $(date +%T)"; python3 $W/lane/run_api_graph.py $W/lane/$tag.json http://127.0.0.1:$PORT 7200; echo "rc=$? in $(( $(date +%s) - t )) s"
  kill $SM; podman logs --timestamps $NAME > $R/$tag.server.log 2>&1
  awk 'NR==2{b=$2} NR>1 && $2>m {m=$2} NR>1 && (n==""||$4<n) {n=$4} END{print "'$tag' base GTT",b,"peak",m,"min avail",n}' $R/$tag.tsv; }
$W/lane/preflight.sh 40 || { echo "preflight refused"; exit 1; }
$W/lane/watchdog.sh 8 wi1745 $R/watchdog.log & WD=$!
trap "kill $WD 2>/dev/null; podman rm -f $NAME >/dev/null 2>&1" EXIT
for s in barrel stump chair bench lantern; do
  serve wi2112/$s; arm 2112_$s
  f=$(ls -t $W/output/3d/wi2112_${s}_*.glb 2>/dev/null | head -1)
  if [ -n "$f" ]; then python3 $W/lane/lane_sidecar.py $f $W/lane/2112_$s.json --models $W/models --checkout $W/ComfyUI-0.37.2 --contracts $W/contracts; echo "sidecar $s rc=$?"; else echo "no glb for $s"; fi
done
echo "== done $(date +%T)"; tail -1 $R/watchdog.log
