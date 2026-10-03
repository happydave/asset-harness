#!/bin/bash
# WI 2112 on ai2: each shape of the test set through WI 2091's chain with its generic rebuild only
# (normalise, voxel remesh and collapse to 300 triangles, a 512 colour bake, LODs, hull, gate), its
# renders against the source (even light, and a low sun), its LOD renders, and what the rebuild kept.
# Run from its folder (~/sandbox-classic-pack/tmp/<WI>) as `taskset -c 12-23 ./shapes.sh` (the ledger
# row's cores; Blender told 12 threads); the source glbs are in src/, the scripts beside this file.
set -u
cd "$(dirname "$0")" || exit 1
B="$HOME/blender-4.2/blender -t 12"
P=.venv/bin/python
# the category's longest horizontal side, in yards
declare -A LONG=([crate]=1.3 [barrel]=0.9 [stump]=1.2 [chair]=0.6 [bench]=2.0 [lantern]=0.35)
# a batch's own sizes, "name size" a line (WI 2120's, from its manifest)
[ -e long.txt ] && while read -r n v; do LONG[$n]=$v; done < long.txt
# OUT names the output folder (default out), UP the normaliser's up mode (stable, the default, or source)
OUT=${OUT:-out}; UP=${UP:-stable}
for s in ${SHAPES:-barrel stump chair bench lantern}; do
  o=$OUT/$s; rm -rf $o; mkdir -p $o
  t=$(date +%s)
  $P normalise.py src/$s.glb ${LONG[$s]} $o/norm.json --up $UP > $o/norm.log 2>&1 || { echo "$s normalise failed"; continue; }
  REBUILD_STEM=$s $B -b --python rebuild.py -- src/$s.glb $o/norm.json 300 512 $o > $o/rebuild.log 2>&1 || echo "$s rebuild rc=$?"
  $P empty.py $o/${s}_300.glb $o/baked_512.png > $o/empty.txt 2>&1
  REBUILD_STEM=$s $P finish.py $o/${s}_300.glb $o/final 300 512 ${LONG[$s]} > $o/finish.log 2>&1; echo "$s gate rc=$?"
  $B -b --python render_glbs.py -- $o/lodrenders $o/final/${s}_lod0.glb $o/final/${s}_lod1.glb $o/final/${s}_lod2.glb > $o/render.log 2>&1
  $P sheet.py $OUT/sheet_$s.png "$s source:$o/render_high_300" "$s rebuilt 300:$o/render_low_300" -- front side above sun > $o/sheet.txt 2>&1
  $P sheet.py $OUT/sheet_${s}_lods.png "$s LOD0:$o/lodrenders/${s}_lod0" "$s LOD1:$o/lodrenders/${s}_lod1" "$s LOD2:$o/lodrenders/${s}_lod2" -- front side above > /dev/null 2>&1
  $P shape_stats.py src/$s.glb $o/norm.json $o/final/${s}_lod0.glb $o/final/finish.json $o/stats.json > /dev/null 2>&1 || echo "$s stats failed"
  echo "$s done in $(( $(date +%s) - t )) s"
done
