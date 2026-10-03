# Findings: five generated props through the game-asset chain's generic rebuild

**Date:** 2026-10-02 · **Work item:** WI 2112 (tickets) · **Hosts:** `gtr` (Z-Image Turbo through
`comfyui.service`; the TRELLIS.2 template arm, ComfyUI v0.37.2, image `localhost/wi1600-comfyui:0.37.2`);
`ai2`, cores 12–23 (Blender 4.2.22 headless, trimesh 4.x, meshoptimizer, Khronos glTF-Validator)

The test input for WI 2092 (the game-asset stage): a barrel and a tree stump (round), a chair and a
bench (open frame) and a lantern (small, detailed), each through sandbox-classic-pack WI 2091's chain
with its **generic rebuild only**: normalise, voxel remesh at 1/96 of the size, collapse to 300
triangles, unwrap, a 512² colour bake from the dense mesh, meshoptimizer LODs, a convex hull, glTF
validation and the budget gate. The per-class rebuild rule is WI 2092's.

The set: [samples-2026-10-02-shape-set/](samples-2026-10-02-shape-set/), one folder per prop
(LOD0–LOD2 glbs, the collision file, the lane's licence sidecar, the normaliser's and gate's
reports, the measurements), the concepts with their recipes, and labelled sheets in `sheets/`
(source against rebuild in three even-light views and a low sun; the three LODs). The dense sources
(about 60 MB each) are not committed: they are on `gtr` at `~/wi1745/output/3d/wi2112_<name>_00001.glb`,
each named by its content hash in its `.lane.json`. The scripts are [prototypes/shape_set/](../prototypes/shape_set/)
and the lane's run script [prototypes/trellis2-comfyui/gpu_pool.sh](../prototypes/trellis2-comfyui/gpu_pool.sh).

## Verdicts

| Prop | Stable pose's tilt | Size (yd, x × y × z) | Faces; LOD1, LOD2 | Bake: worst view; black | Source to rebuild: p95; max | Pieces | Hull tris; over volume | Gate |
|---|---|---|---|---|---|---|---|---|
| crate (WI 2091, control) | 0° | 1.30 × 1.17 × 0.89 | 300; 150, 112 | 3.0 %; 0.2 % | 2.1 %; 4.4 % | 1, closed | 120; 1.186 | pass |
| barrel | 180° | 0.90 × 0.90 × 1.06 | 300; 150, 74 | 2.1 %; 0.1 % | 3.3 %; 5.3 % | 1, closed | 238; 1.059 | pass |
| stump | 1° | 1.20 × 1.19 × 0.74 | 300; 212, 73 | 1.5 %; 15.9 % | 1.9 %; 4.6 % | 1, closed | 66; 1.842 | pass |
| chair | 88° | 0.60 × 0.54 × 1.01 | 300; 202, 44 | 0.8 %; 0.1 % | 2.1 %; 4.5 % | 1, closed | 50; 5.176 | pass |
| bench | 180° | 2.00 × 1.64 × 0.64 | 300; 288, 58 | 1.3 %; 0.2 % | 1.3 %; 3.4 % | 1, closed | 70; 6.832 | pass |
| lantern | 91° | 0.35 × 0.35 × 0.97 | 257; 158, 31 | 6.3 %; 1.3 % | 2.6 %; 4.5 % | 48, open | 26; — | pass |

Columns: the stable pose's tilt is how far the WI 2091 normaliser's stable-pose rule would turn the
prop off the generator's own up (180° = turned over); size after normalising with the source's up;
the bake's worst mean-colour difference from the dense source over four views, and the share of
near-black texels in its islands; the distance from 20,000 points on the dense source to the rebuild,
as a share of the prop's size; connected pieces of the rebuild, welded on position, and whether it is
closed; the hull's triangles and its volume over the rebuild's.

- **The generic rebuild holds for round, chunky and open-frame props at 300 triangles** (barrel,
  stump, chair, bench): one closed piece each, the source within 3.3 % of the size at p95, the bake
  within 2.1 % in every view. Looked at: the barrel's hoops and rivets, the chair's slats and
  stretchers and the bench's trestles all survive. The outline is a little polygonal at the barrel's
  base; the stump's thin, rounded roots become flat triangular blades. *Confirmed* for these four, at
  this stylised, chunky proportion (the concepts' "clean readable shapes").
- **It fails on the small, detailed prop.** The lantern's peaked roof collapses to a flat plate, its
  ring breaks into floating fragments and the frame comes apart: 48 pieces, open, 257 faces. The
  candle and the base survive. **The gate passed it.** Neither the budget gate nor glTF validation
  looks at connectivity, and the source-to-rebuild distance stays small (p95 2.6 %) because the lost
  parts are thin. The piece count is the signal: a closed source part that the rebuild turns into
  many pieces.
- **The normaliser's stable-pose rule is wrong for furniture and symmetric props.** It laid the chair on
  its back (88°), and turned the bench, the barrel and the lantern over or onto a side (180°, 180°,
  91°); the crate and the stump came through upright. TRELLIS.2 wrote all six upright, so the set was
  run again keeping the source's up (`normalise.py --up source`; the stable reading stays in the
  report), which is the set placed here. Both runs are on `ai2` (`out/`, `out_up/`); the stable-pose
  sheets of the chair and bench are in `sheets/`. Pixal3D's tilted output (WI 2091) still needs a
  correction, so the rule is per generator. *Confirmed* for TRELLIS.2 on these six.
- **Scaling by the longest horizontal side mis-sizes tall props.** The lantern at 0.35 yards across
  comes out 0.97 tall. A post, a lantern or a candelabra wants its category height.
- **Convex hulls fit open frames badly:** 5.2 times the chair's volume, 6.8 times the bench's, 1.8 the
  stump's (its spreading roots). The crate and barrel are near 1. A walker is stopped by the hull, so
  a chair or bench blocks the space under its seat.
- **LOD1 often stops short of half.** The attribute-aware simplifier stopped at 202 (chair), 212
  (stump) and 288 (bench) against 150, at its 5 % error bound; LOD2 reached 31–74 against 75.
- **The bench was generated askew,** its seat turned across its trestles. That is the lane, not the
  chain (visible in the source render); the rebuild keeps it faithfully, and the footprint is near
  square (2.0 × 1.64).
- **The stump's 15.9 % near-black texels are its bark,** which is that dark in the source (mean about
  40/255); the bake check is not failing.

## The lane: TRELLIS.2 at a 1,024 upsample target

The template's upsample target is 1,536. **The barrel at 1,536 did not finish in two hours:** the
shape decode ran from 18:08:39 to 20:03:26 (115 min, against 18.5 min for the crate in WI 1751 on the
same lane), the GPU at full clock throughout (2,900 MHz, 103 W), GTT peak 58,140 MiB, at least
50,404 MiB available; the driver's 7,200 s limit stopped it in the texture stage. At 1,024 the same
barrel decoded to 14,296,704 vertices (the crate's 1,536 decode is 12.9M) in 19 min, and the whole
run took 1,411 s. The other four at 1,024: stump 720 s, chair 400 s, bench 280 s, lantern 160 s.
The chain rebuilds every prop to 300 triangles at 1/96 of its size, so the 1,024 decode loses
nothing it uses; the texture stage and its 4,096 bake are unchanged. **For game props, 1,024 is the
target** (about a sixth of the decode time on the barrel); 1,536 is for the dense asset itself. *Supported*
(one barrel at 1,536; the cause of its slowness, beyond a larger decode, is not established).

The concepts came from **Z-Image Turbo**, not Base: `gtr`'s `comfyui.service` has only Turbo, and
its models are the owner's. Turbo varies little with the seed, so two seeds were made and seed 11
was taken for every shape, by rule rather than by look; all ten were usable (`concepts/`).

## For WI 2092

- A connectivity check in the gate: the rebuild's pieces against the source's closed parts, or at
  least a refusal of a rebuild in many pieces.
- The up axis by generator: TRELLIS.2's kept, Pixal3D's corrected; the stable pose as a check, never the
  rule for furniture.
- The scale by the category's governing dimension (height for tall props).
- Collision by class: a hull for closed round and box props, something else for open frames (a box
  under the seat, or per-leg boxes).
- The generic rebuild for chunky round and open-frame props at this proportion; a different route for
  small detailed props with thin parts (the lantern), and the fitted primitive for hard-surface boxes
  (WI 2091).
- The TRELLIS.2 upsample target at 1,024 for game props.

The licence status of every prop is the lane's: `conditional` until WI 1749's O1 and O2, recorded in
each `.lane.json`.
