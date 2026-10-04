# stage — the game-asset stage for generated static props

One command that takes a generated prop from the 3D lane (a dense TRELLIS.2 glb and its lane record) to
a game asset, or refuses it. The asset is a glb at its category's triangle budget, with LODs, a
collision mesh, a fixed up axis and scale, sheets under even light and the consumer's light, and a
sidecar. It exits non-zero, with the reasons, when no arm passes the gate. Graduated from the
prototypes of WIs 2091, 2112 and 2120 (`../prototypes/shape_set/`); the findings are
[2026-10-03-game-asset-stage.md](../findings/2026-10-03-game-asset-stage.md) and, for its second pass
(WI 2143), [2026-10-03-game-asset-stage-second-pass.md](../findings/2026-10-03-game-asset-stage-second-pass.md).

```sh
python3 stage.py SOURCE.glb --category NAME --table consumers/sandbox-classic-pack.json \
    --rig rigs/sandbox-classic-pack.json --out DIR [--provisional provisional.json]
python3 stage.py SOURCE.glb ... --control trellis2     # no lane record: a control, the generator named
python3 batch.py LIST.json OUTDIR --cpus 12-23          # one prop at a time, under taskset on that slice
python3 test_stage.py [--fast]                          # the tests; --fast skips the Blender cases
```

Run it in the venv that has trimesh, numpy, scipy, networkx, rtree, pillow and meshoptimizer. On `ai2`,
that is `~/sandbox-classic-pack/tmp/2091/.venv`. It also needs Blender 4.2 (`STAGE_BLENDER`, default
`~/blender-4.2/blender`), glTF-Validator (`STAGE_VALIDATOR`, default `bin/gltf_validator` beside the
stage) and a thread count for Blender (`STAGE_THREADS`, default 12). A missing tool exits 2, naming it.
Exit codes: 0 accepted, 1 refused, 2 wrong inputs or tools.

## Inputs

- **The source and its lane record** (`SOURCE.glb.lane.json` beside it, or `--lane PATH`). The record's `arm` names the generator,
  and `asset.content_hash` must match the source. Only TRELLIS.2 (`trellis2`) is supported. Its up
  axis is kept: the stable resting pose is measured and recorded, never applied, since it lays a chair
  on its back. A source without a record runs only when declared a control.
- **The consumer table** (`consumers/*.json`): per category, a `class`, a `governing` axis
  (`horizontal`, the longest horizontal side; or `height`), a `size` in yards on that axis, a triangle
  `budget` for LOD0 and a `texture` size. The stage holds no consumer's numbers.
  `consumers/sandbox-classic-pack.json` covers the 29 categories of WIs 2112 and 2120. Its rows name
  where each size came from: the tall categories' heights from the Elwynn pack's most-placed model of
  the kind, and two labelled guesses.
- **The light rig** (`rigs/*.json`): lightings `noon` and `low`, each a sun elevation and azimuth,
  colour and strength, an ambient colour and strength, and an exposure. `rigs/sandbox-classic-pack.json`
  takes Elwynn's light keys from the pack, as the client decodes them, and is calibrated against WI
  2091's in-game capture. It records its sources.
- **An optional provisional record**, carried into the sidecar unchanged.

## Which arm for which class

Arms are tried in order; the first whose output passes the gate is accepted. Every arm tried is
recorded with its failing rows.

| Class | Arms in order | Collision |
|---|---|---|
| box | box, generic | the fitted box (box arm), else the convex hull |
| round | lathe | the convex hull |
| open frame | generic, parts | one oriented box per source part |
| small detailed | parts, generic | the convex hull |
| cluster | parts, generic | one oriented box per source part |
| organic | generic, parts | the hull when at most 1.5 times the rebuild's volume, else one box per part |
| flat | planar, generic | the oriented box |
| slab | box, generic | the oriented box |

- **generic:** a voxel remesh at the finest of size/96, /72, /56 and /48 whose pieces do not exceed
  the source's parts, then a collapse to the budget. Islands under 0.5 % of the area are dropped as
  debris.
- **box:** a bevelled box fitted to the body: each face but the bottom moves in past up to 5 % of the
  source's surface samples, never shortening the governing axis by more than 2.5 %, and the trim with
  the best two-way fit is taken. A box on the extremes stands off the body by its latches and caps.
- **planar:** a coarse remesh, a collapse, and near-flat faces merged.
- **lathe:** a surface of revolution about the most circular axis. The axis runs through circles fitted
  to the body's cross-sections, not the bounding box's centre, which a handle or a cradle pulls aside.
  Its closed profile runs along the bottom surface, up the outer side and across the top, revolved with
  12–16 sides (the closest fit wins). For an open vessel, whose top seen from above drops more than a
  quarter of its height inside the rim, the profile runs over the rim and down the inner wall to the
  inside floor. Parts standing out of it by 4 % or more are rebuilt by the parts arm and joined.
- **parts:** each source part rebuilt on its own by a box, a lathe or its own simplification, whichever
  fits within 4 % both ways. Each part gets 12 triangles, and the rest of the budget is shared by area.

Every arm unwraps its rebuild and bakes the source's base colour onto it with Cycles (the source's
material flattened to metallic 0 and roughness 1). LOD1 and LOD2 come from meshoptimizer at about a
half and a quarter. The arms for the Blender work are in `blender_rebuild.py`; the lathe and parts
geometry is built in `parts.py`.

A source's **parts** are its welded components merged where they lie within 1 % of the size of each
other (on a grid of cells that size, so parts up to about 3.5 % apart can merge), each at least 1 % of
its area. TRELLIS.2 sources come in many fragments, up to 346 on WI 2120's hanging lantern, so a raw
count says nothing.

## The gate

Each row is recorded with its value and limit; any failed row refuses the arm.

| Row | Limit |
|---|---|
| triangles | LOD0 within the budget |
| lods_decrease | LOD1 below LOD0, LOD2 below LOD1 |
| texture | within the category's |
| foot_on_ground | lowest point at height 0 within 1 mm |
| size | the governing axis within 5 % of the category's size |
| collision | present and closed |
| pieces | the rebuild's pieces, counted by the source-part rule, no more than the source's parts |
| floating | no piece further than 1 % of the size from every other piece and the ground |
| shape | p95 distance within 4 % of the size (6 % for the box arm), the larger of two directions: source to rebuild (source points buried more than 2 % inside any closed piece of the rebuild left out, TRELLIS.2's internal surfaces) and rebuild to source |
| colour | the front, side and back even-light views' mean colour each within 5 % of the source's, the view from above within 8 % |
| gltf_validator | 0 errors on each LOD |

The consumer-light sheet is not a gate row: facets and folds under a low sun are judged by eye.

The box arm's shape limit is its own because a fitted box cannot follow faces sculpted in relief:
WI 2091's crate, cleanest as a box by eye, reads 5.73 %. The view from above has its own colour limit
because it sees top faces and shelf interiors at a slant, while in play the camera stands near a prop's
side.

## Changing a row or arm

- **Each changed row, arm or measure gets a test where it should refuse,** not only one where it should
  excuse. A measure carried from a prototype into the gate once excused a box around a sphere, since
  only the direction it was built for was tested.
- **Diagnose a wrong verdict on the prop before changing a rule for it.** WI 2143 found two of WI 2092's
  readings wrong this way:
  - the tombstone's ground patch was lost by the remesh, not the debris rule;
  - the mug's lathe was off-centre, not short of its handle.
- **Re-score on the whole set and read every changed verdict by eye.** A limit chosen on a few props is
  supported on those props only.

## Outputs

Before it runs, the stage removes this stem's earlier outputs from `--out` (its LODs, collision,
sidecar, sheets, `norm.json` and `arms/`), so a refusal never leaves an earlier run's accepted asset
behind. It deletes nothing outside `--out`; `removable` in `stage.py` is the check.

In `--out`:
- for an accepted prop, `<stem>_lod0.glb`, `_lod1`, `_lod2` and `<stem>.collision.json` (the glb's own
  frame, y up, yards, with bounds);
- `norm.json`;
- `<stem>_sheet_even.png` and `<stem>_sheet_consumer_light.png` (the best attempt's, when refused);
- every arm's working files under `arms/`;
- `<stem>.stage.json`: the result, the source's name and hash, control or not, the lane and
  provisional records unchanged, the category's row, the normalisation, the source's parts, the class,
  every arm tried with its geometry, measurements, gate rows and Blender's peak resident memory
  (`blender_peak_mb`), the accepted arm, LOD triangle counts, texture, collision and the gate.

`batch.py` writes `batch.jsonl`, one row a prop. Before any prop it refuses, naming what it saw, when
its CPU affinity is not the slice it was given or a source's hash differs from its lane record. The
ledger row is checked by whoever starts it, on the host that holds the ledger.

`control_2120.py` runs the gate's new rows over WI 2120's generic outputs with no rebuild: the control
that they refuse what that gate passed.
