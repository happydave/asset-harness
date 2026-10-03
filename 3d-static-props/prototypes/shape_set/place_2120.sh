#!/bin/bash
# WI 2120, from ai: copy each chained prop from ai2 into the asset-harness findings folder, with the
# lane sidecar, the reports and a provisional.json carrying both marks; sheets as webp.
#   place_2120.sh NAME...
set -eu
D=/home/notdave/Documents/projects/asset-harness/3d-static-props/findings/samples-2026-10-02-zone-pool
M=/home/notdave/Documents/projects/asset-harness/3d-static-props/prototypes/shape_set/zone_pool_manifest.json
R=sandbox-classic-pack/tmp/2120
mkdir -p "$D/sheets" "$D/.png"
for s in "$@"; do
  mkdir -p "$D/$s"
  scp -q "ai2:$R/out/$s/final/*" "ai2:$R/out/$s/norm.json" "ai2:$R/out/$s/stats.json" "ai2:$R/src/$s.glb.lane.json" "$D/$s/"
  scp -q "ai2:$R/out/sheet_$s.png" "ai2:$R/out/sheet_${s}_lods.png" "$D/.png/"
  python3 - "$M" "$s" "$D/$s/provisional.json" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
item = next(i for i in m["items"] if i["name"] == sys.argv[2])
json.dump({"work_item": m["work_item"], "name": item["name"], "group": item["group"], "class": item["class"],
           "provisional": m["provisional"], "ships": False}, open(sys.argv[3], "w"), indent=2)
EOF
done
python3 - "$D" <<'EOF'
import pathlib, sys
from PIL import Image
d = pathlib.Path(sys.argv[1])
for p in sorted((d / ".png").glob("*.png")):
    Image.open(p).save(d / "sheets" / (p.stem + ".webp"), quality=85)
    p.unlink()
(d / ".png").rmdir()
EOF
