# Findings: a zone's candidate pool through the generic chain, by shape class

**Date:** 2026-10-02 to 03 · **Work item:** WI 2120 (tickets) · **Hosts:** `gtr` (Z-Image Turbo through
`comfyui.service`; the TRELLIS.2 template arm at an upsample target of 1,024, ComfyUI v0.37.2, image
`localhost/wi1600-comfyui:0.37.2`); `ai2`, cores 12–23 (Blender 4.2.22 headless, trimesh 4.x,
meshoptimizer, Khronos glTF-Validator)

**Provisional, twice.** The style is unanchored until WI 2093 (no style guide, anchor set or style
LoRA exists; the prompts are re-run once it lands). The licence is the lane's `conditional` until WI
1749's O1 and O2. Nothing here ships. Each prop's `provisional.json` carries both marks and
`"ships": false`; each `.lane.json` carries the licence record.

One generated prop for each of the 27 hard-surface categories among Elwynn's most-placed doodads
([prototypes/shape_set/zone_pool_manifest.json](../prototypes/shape_set/zone_pool_manifest.json): the
name, the group, the shape class, the category's longest side and the subject prompt), foliage out of
scope. Each through the chain of WIs 2091 and 2112 with its **generic rebuild only**, keeping the
source's up (WI 2112's finding): normalise, voxel remesh at 1/96 of the size, collapse to 300
triangles, unwrap, a 512² colour bake, meshoptimizer LODs, a convex hull, glTF validation and the
budget gate. The per-class rule is WI 2092's; this is its test input and its hit rate.

The set: [samples-2026-10-02-zone-pool/](samples-2026-10-02-zone-pool/), one folder per prop (LOD0–LOD2
glbs, the collision file, the lane sidecar, `provisional.json`, the normaliser's, gate's and
measurement reports), `concepts/` (27 stills with their recipes), `sheets/` (source against rebuild
in three even-light views and a low sun; the three LODs) and `look.json` (the sheets read by eye).
The dense sources (about 60 MB each) stay on `gtr` at `~/wi1745/output/3d/wi2120_<name>_00001.glb`,
each named by its content hash in its `.lane.json`.

## Hit rate by shape class

A prop **holds by the numbers** when the rebuild is one closed piece, the source is within 4 % of the
size at p95 (internal surfaces left out, below) and the bake is within 5 % of the source in every view.
WI 2112's four holders reached 3.3 % and 2.1 %. A prop **holds by look** when its sheet reads as the
same object, by eye (`look.json`, one reader, the author). A **hit** needs both.

| Class | Props | Hold by the numbers | Hold by look | Hits |
|---|---|---|---|---|
| open frame | 8 | 4 | 6 | 4 |
| round | 5 | 3 | 2 | 2 |
| box | 4 | 1 | 3 | 1 |
| cluster | 3 | 0 | 1 | 0 |
| organic | 3 | 1 | 1 | 1 |
| small detailed | 2 | 0 | 0 | 0 |
| flat | 1 | 1 | 1 | 1 |
| slab | 1 | 0 | 1 | 0 |
| **all** | **27** | **10** | **15** | **9** |

**The gate passed 26 of 27.** It caught only the cliff rock, and that on its triangle count. The nine
hits are the barrel, bottle, chest, Elwynn fence, table, chair, weapon rack, rug and rock.

| Prop | Class | Pieces | p95 | Worst view | Gate | Numbers | Look | Note |
|---|---|---|---|---|---|---|---|---|
| barrel | round | 1 | 1.6 % | 1.9 % | pass | hold | hold | hoops and staves kept |
| jar | round | 1 | 1.3 % | 2.0 % | pass | hold | fail | rim faceted to an octagon, the lug handles become spikes |
| bottle | round | 1 | 1.6 % | 1.0 % | pass | hold | hold | cork and neck kept |
| keg | round | 15 | 3.4 % | 4.1 % | pass | fail | fail | the body goes octagonal (15 pieces, as the source's 14) |
| mug | round | 5 | 3.5 % | 4.5 % | pass | fail | fail | octagonal, the handle shears, the foam faceted |
| chest | box | 1 | 1.6 % | 1.5 % | pass | hold | hold | bands, lock plate and studs kept |
| crate | box | 1 | 6.0 % | 12.4 % | pass | fail | fail | generated open-topped; the thin walls' lower half is lost, the floor hangs in the frame |
| bookshelf | box | 1 | 1.7 % | 6.8 % | pass | fail | hold | generated as a closed cabinet, shelves to one side |
| planter_box | box | 4 | 3.8 % | 3.3 % | pass | fail | hold | the box holds; the plants thin to a few leaves |
| elwynn_fence | open frame | 1 | 1.1 % | 1.6 % | pass | hold | hold | posts and rails kept |
| westfall_fence | open frame | 24 | 2.2 % | 2.7 % | pass | fail | hold | reads right at this size; the planks come apart |
| iron_gate | open frame | 8 | 2.5 % | 13.0 % | pass | fail | fail | the bars fuse into a dark sheet with fins; finial gone |
| post_light | open frame | 3 | 1.0 % | 4.7 % | pass | fail | hold | the lamp hangs free of the arm |
| candelabra | open frame | 19 | 2.1 % | 2.9 % | pass | fail | fail | candles become spikes, the arms thin out |
| table | open frame | 1 | 1.4 % | 1.3 % | pass | hold | hold | top, legs and stretchers kept |
| chair | open frame | 1 | 1.2 % | 0.8 % | pass | hold | hold | slat back, seat and stretchers kept |
| weapon_rack | open frame | 1 | 1.0 % | 3.1 % | pass | hold | hold | rack, blades and axe head kept |
| lantern | small detailed | 50 | 2.6 % | 6.1 % | pass | fail | fail | the ring floats free, the roof goes flat |
| hanging_lantern | small detailed | 30 | 2.0 % | 7.2 % | pass | fail | fail | the bail is lost; the lantern floats under the bracket |
| utensils | cluster | 5 | 1.6 % | 6.5 % | pass | fail | fail | the pot and bowls go hexagonal |
| book_stack | cluster | 1 | 1.8 % | 8.0 % | pass | fail | hold | covers and page edges kept |
| tools | cluster | 3 | 1.1 % | 7.0 % | pass | fail | fail | the rake's tines fuse into a blade |
| hay_pile | organic | 73 | 3.5 % | 29.9 % | pass | fail | fail | the straw fringe is lost: a smooth dome |
| rock | organic | 1 | 1.3 % | 0.8 % | pass | hold | hold | faithful |
| cliff_rock | organic | 99 | 2.2 % | 9.4 % | **fail** | fail | fail | torn into slivers with black gaps; 2,292 faces |
| rug | flat | 1 | 0.6 % | 4.4 % | pass | hold | hold | border and fringe kept in the bake |
| tombstone | slab | 5 | 1.8 % | 2.1 % | pass | fail | hold | stone, base and ground kept; the cross faint |

## What the batch shows

- **The generic rebuild suits chunky closed shapes and solid-member frames**: barrels, bottles,
  chests, rocks, rugs, tables, chairs, a rail fence and a weapon rack. *Confirmed* on these nine, at
  the concepts' stylised proportion. It carries WI 2112's barrel and chair results over to fresh
  generations.
- **At 300 triangles, small round bodies go polygonal.** The jar, keg, mug and the pot and bowls come
  out with six to eight sides. The barrel and bottle hold because they are large enough, or narrow
  enough, for the budget. Round props want a higher budget or a fitted primitive (a lathe), by class.
- **Thin parts are lost or come loose**: handles, bails, rings, tines, candles, bars, straw. Every
  prop with them fails, and the piece count is the signal (WI 2112's finding, now on ten props). It
  has to be read against the source's (`stats.json`, pieces over 50 faces): the lantern goes from 5
  to 50, but the keg's 15 and the candelabra's 19 match their sources' 14 and 21. A
  raw count also over-refuses. The post light's lamp hangs free in the source too (7 pieces, 3 rebuilt),
  and the Westfall fence goes from 6 to 24 yet reads right at this size.
- **Thin-walled hollow boxes fail differently.** The open-topped crate is one piece by count, yet half
  its wall is gone. The p95 (6.0 %) and the worst view (12.4 %) catch it where the piece count does
  not.
- **The gate is not a quality check.** Its one refusal was a triangle count; it passed the lantern, the
  iron gate and the hay pile. WI 2092's gate wants the piece count against the source's, the p95 and
  the worst view.
- **The numbers and the look disagree in both directions.** The jar holds by the numbers yet its
  handles are spikes. The book stack and the bookshelf hold by look yet miss the 5 % bake bar (8.0 %
  and 6.8 %), in the view from above only, where the rebuild reads lighter; their other three views
  are within 2.1 %. The numbers screen and the
  look decides; neither alone is the hit rate.
- **Scaling by the longest horizontal side mis-sizes tall props** (WI 2112's finding again): the
  bookshelf comes out 3.5 yards tall and the weapon rack 3.4, both from a 1.4–1.5 yard footprint.
- **The lane's generation is not the concept's object every time.** The crate came out open-topped
  and the bookshelf as a closed cabinet. The concept stage, not the chain, decides those (WI 2093).
- **The lantern repeats WI 2112's** (the same prompt and seed): 50 pieces here against 48 there, and
  the same failure. The lane and the chain are stable run to run.

## The measurement: internal surfaces

`shape_stats.py`'s source-to-rebuild distance counts surfaces **inside** TRELLIS.2's meshes as
lost. TRELLIS.2 leaves them where parts meet: between stacked books, under a chest's lid, inside a
barrel. A closed rebuild drops them, rightly. The book stack read 20.6 % at p95 and the chest 6.8 %,
while their sheets match the source. Every source point farther than 4 % from the rebuild lay inside
it: 7,516 of 20,000 on the book stack, 6,878 on the chest. [prototypes/shape_set/outside.py](../prototypes/shape_set/outside.py)
leaves out source points inside a closed rebuild and deeper than 2 % of the size. Open rebuilds keep
every point. That brings the book stack to 1.8 % and the chest to 1.6 %; the open crate stays at
6.0 %. The table above uses it, and each prop's `outside.json` records it beside the raw figure in
`stats.json`. *Supported*: the 2 % depth is a choice, not a calibration. The script is the code that
ran, moved into a file, and was not run again from the file.

## The lane

All 27 generated at the 1,024 upsample target, one at a time, from 20:59 to 02:03 (5 h 4 min).
Most took 2–7 minutes. The barrel (24), crate (21), keg (20), chest (14), cliff rock (14), jar (13)
and rock (10) took longer, and two were outliers: the book stack took 76 minutes and the mug 42.
Both finished normally; the cause is not established. Concepts are Z-Image Turbo through
`comfyui.service`, seed 11 for every prop by rule (WI 2112), all 27 usable.

## For WI 2092

- The gate: the rebuild's pieces against the source's, the p95 without internal surfaces, the worst
  view. The current gate refused one prop in 27.
- The route by class:
  - the generic rebuild for chunky closed props and solid-member frames;
  - a higher budget or a lathe for small round bodies;
  - another route for thin parts (handles, bails, bars, tines, candles), or keep them as separate
    modelled pieces;
  - the fitted box (WI 2091) for closed boxes;
  - a thin-wall route, or a closed concept, for open boxes.
- Scale by the category's governing dimension: height for shelves, racks, posts and lights.
- Organic piles and broken rock (the hay pile's straw, the cliff's slabs) are outside this chain's
  reach at 300 triangles; the boulder holds.
