#!/bin/sh
# Fetch the gate's vendored tools into vendor/ (gitignored). Nothing is installed on the host and no
# Node is needed: the two npm packages are plain tarballs from the registry.
#
#   glTF-Validator   2.0.0-dev.3.10  Apache-2.0  Khronos; released 2024-10-22
#   three            0.169.0         MIT         the version asset-studio's viewer-core pins
#   @pixiv/three-vrm 3.5.5           MIT         same
#
# The hashes are of the files as first fetched on 2026-09-17. Khronos publishes no checksum; the two npm
# hashes were checked against the registry's own dist.integrity on that date. A mismatch stops the script
# before anything is unpacked.
set -eu
cd "$(dirname "$0")"
rm -rf vendor.tmp && mkdir vendor.tmp

fetch() { # url sha256 name
  curl -fsSL -o "vendor.tmp/$3" "$1"
  echo "$2  vendor.tmp/$3" | sha256sum -c - >/dev/null || { echo "sha256 mismatch for $3 — not unpacking" >&2; exit 1; }
}

fetch https://github.com/KhronosGroup/glTF-Validator/releases/download/2.0.0-dev.3.10/gltf_validator-2.0.0-dev.3.10-linux64.tar.xz \
  168eba887964125abe17ae97899b38d0b3cfd73c266c78424c194929ddcbc522 gltf_validator.tar.xz
fetch https://registry.npmjs.org/three/-/three-0.169.0.tgz \
  c86d0937570fb425d981e156ddf919c43dbc45d4e91fd7c8dd0de56723b3ec71 three.tgz
fetch https://registry.npmjs.org/@pixiv/three-vrm/-/three-vrm-3.5.5.tgz \
  6f0102f987bc8abc9b9e78ef5b3259ea9f0dc51e30bf51d32aea6218394ea755 three-vrm.tgz

mkdir -p vendor.tmp/gltf_validator vendor.tmp/three/examples/jsm vendor.tmp/unpack
tar -xJf vendor.tmp/gltf_validator.tar.xz -C vendor.tmp/gltf_validator
tar -xzf vendor.tmp/three.tgz -C vendor.tmp/unpack
cp vendor.tmp/unpack/package/build/three.module.js vendor.tmp/three/
cp vendor.tmp/unpack/package/LICENSE vendor.tmp/three/
cp -r vendor.tmp/unpack/package/examples/jsm/loaders vendor.tmp/unpack/package/examples/jsm/utils vendor.tmp/three/examples/jsm/
rm -rf vendor.tmp/unpack && mkdir vendor.tmp/unpack
tar -xzf vendor.tmp/three-vrm.tgz -C vendor.tmp/unpack
cp vendor.tmp/unpack/package/lib/three-vrm.module.js vendor.tmp/
cp vendor.tmp/unpack/package/LICENSE vendor.tmp/three-vrm.LICENSE
rm -rf vendor.tmp/unpack vendor.tmp/*.tgz vendor.tmp/*.tar.xz

rm -rf vendor && mv vendor.tmp vendor
echo "vendor/ ready ($(du -sh vendor | cut -f1))"
