#!/bin/bash
# WIs 2112 and 2120, from ai: for each name, wait until gtr's run script (its log results/<WI>.log) has
# written the prop's sidecar, skipped it or given up, then pull it to ai2 and run the chain on the
# reserved cores. Stops before the next name when $S/STOP_<WI> exists (a pause for ai2 between props).
#   follow.sh WI NAME...
S=$(dirname "$0"); WI=$1; shift
for s in "$@"; do
  [ -e $S/STOP_$WI ] && { echo "== paused before $s $(date +%T)"; exit 0; }
  until ssh -n gtr "grep -q 'sidecar $s rc\|no glb for $s\|== $s exists\|no input for $s\|== stopped before $s' ~/wi1745/results/$WI.log"; do sleep 30; done
  line=$(ssh -n gtr "grep -E 'sidecar $s rc|no glb for $s|== $s exists|no input for $s|== stopped before $s' ~/wi1745/results/$WI.log | tail -1")
  echo "== $s $(date +%T): $line"
  case "$line" in "sidecar $s rc=0"|"== $s exists, skipped") $S/pull_and_chain.sh $WI $s ;; esac
done
echo "== all done $(date +%T)"
