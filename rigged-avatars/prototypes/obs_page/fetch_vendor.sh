#!/bin/sh
# WI 1370 spike — fetch the vendored web dependencies. All three are licence-clean, verified from
# primary text at adoption (2026-09-07):
#   three            0.169.0  MIT           (copied from asset-studio's node_modules; no npm on this host)
#   @pixiv/three-vrm 3.5.5    MIT           (same)
#   @mediapipe/tasks-vision 0.10.14 Apache-2.0, code AND released weights — the inverse of the AMASS
#                                           pattern: the entity owning the restricted corpus grants the
#                                           permissive licence (WI 923).
# vendor/ is gitignored: ~27 MB of wasm and model weights do not belong in the repo.
set -eu
cd "$(dirname "$0")"
NM=${NM:-../../../../asset-studio/node_modules}
mkdir -p vendor/three/examples/jsm
cp "$NM/three/build/three.module.js" vendor/three/
cp -r "$NM/three/examples/jsm/loaders" "$NM/three/examples/jsm/utils" vendor/three/examples/jsm/
cp "$NM/@pixiv/three-vrm/lib/three-vrm.module.js" vendor/
curl -sSL -o vendor/tasks-vision.tgz \
  https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-0.10.14.tgz
tar xzf vendor/tasks-vision.tgz -C vendor && rm vendor/tasks-vision.tgz
rm -rf vendor/mediapipe && mv vendor/package vendor/mediapipe
curl -sSL -o vendor/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
echo "vendor/ ready ($(du -sh vendor | cut -f1))"
