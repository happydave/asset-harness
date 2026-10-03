#!/bin/bash
# WI 2112/2120, from ai: copy one generated prop and its lane sidecar from gtr to ai2, then run the
# chain on it there on the reserved cores. Usage: pull_and_chain.sh WI SHAPE   (WI = 2112 or 2120)
set -u
wi=$1 s=$2
f=$(ssh -n gtr "ls -t ~/wi1745/output/3d/wi${wi}_${s}_*.glb 2>/dev/null | head -1")
[ -n "$f" ] || { echo "$s: no glb on gtr"; exit 1; }
d=sandbox-classic-pack/tmp/$wi
scp -q -3 "gtr:$f" "ai2:$d/src/$s.glb" && scp -q -3 "gtr:$f.lane.json" "ai2:$d/src/$s.glb.lane.json" || { echo "$s: copy failed"; exit 1; }
ssh -n ai2 "cd ~/$d && UP=${UP:-stable} SHAPES=$s taskset -c 12-23 ./shapes.sh"
