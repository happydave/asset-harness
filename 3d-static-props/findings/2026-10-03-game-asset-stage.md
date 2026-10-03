# Findings: the game-asset stage, a rebuild rule per shape class, scored on WIs 2112 and 2120's sets

**Date:** 2026-10-03 · **Work item:** WI 2092 (tickets) · **Host:** `ai2`, cores 12–23 (Blender
4.2.22 headless, trimesh 5.1.1, meshoptimizer 0.2.30a0 through its library, glTF-Validator
2.0.0-dev.3.10) · **The stage:** [../stage/](../stage/README.md)

**Provisional, twice, as WI 2120's set was.** The style is unanchored until WI 2093, and the licence is
the lane's `conditional` until WI 1749's O1 and O2. Each sidecar carries its source's lane record
unchanged, and WI 2120's carry their provisional records too. WI 2112's six had none, and the WI 2091
crate control has no lane record. Nothing here ships.

The stage takes a TRELLIS.2 prop through its class's rebuild arms in order and accepts the first whose
output passes the gate. The arms are box, lathe, generic, planar and parts. The gate adds four rows to
WI 2120's:
- pieces against the source's parts;
- no floating part;
- a two-way shape distance;
- colour by view.

It was run once on each of WI 2120's 27 props and WI 2112's six (five plus the WI 2091 crate as a
control). The set: [samples-2026-10-03-game-asset-stage/](samples-2026-10-03-game-asset-stage/), one
folder a prop:
- for an accepted prop, its LODs and collision;
- the sidecar and the normalisation;
- both sheets as webp in `sheets/`;
- `look.json`, the sheets read by eye: one reader, the author, as in WI 2120.

## Hit rate by shape class (WI 2120's 27, against its 9)

A **hit** is a prop the gate accepts whose look holds. WI 2120's hits were props whose numbers and look
both held under its prototype chain, so the two columns compare the chain's verdict with the eye on the
same 27 sources. Its hits counted 9.

| Class | Props | Accepted | Hold by look | Hits | WI 2120's hits |
|---|---|---|---|---|---|
| open frame | 8 | 6 | 6 | 6 | 4 |
| round | 5 | 5 | 2 | 2 | 2 |
| box | 4 | 2 | 3 | 2 | 1 |
| cluster | 3 | 0 | 1 | 0 | 0 |
| organic | 3 | 1 | 1 | 1 | 1 |
| small detailed | 2 | 1 | 1 | 1 | 0 |
| flat | 1 | 1 | 1 | 1 | 1 |
| slab | 1 | 0 | 1 | 0 | 0 |
| **all** | **27** | **16** | **16** | **13** | **9** |

**The gate and the look agree on 21 of 27; WI 2120's gate agreed on 16.**
- **False accepts: 3** (WI 2120's: 11): the jar, the keg and the mug, round props whose lathe failed and
  whose generic rebuild passed every row but still reads faceted.
- **False refusals: 3** (WI 2120's: 0):
  - the bookshelf (colour 7.4 % from above) and the book stack (6.1 % from above), both faithful in
    every other view;
  - the tombstone, whose generic rebuild is faithful. It was refused on size: the debris rule dropped
    slivers of its ground patch, the prop's widest extent, 0.69 against 0.8.

*Supported*: one run a prop, one reader. The chain is deterministic at these settings: two early runs
of three props gave identical gate values.

WI 2112's six: the barrel (lathe), stump, chair, bench and crate control (generic) are accepted, and
all hold by look. The lantern is refused (the parts arm loses its top ring), and its look fails too: 6
of 6 agree.

## What each arm did

- **The lathe** carries round bodies the generic arm made six- to eight-sided. Both barrels and the
  bottle were accepted with 12–16 sides and their hoops kept. It needed a closed profile (bottom
  surface, outer side, top surface), since the silhouette alone capped the barrel's recessed lid flat.
  - **The jar's lathe misses by 22 % from rebuild to source,** cause not found; the generic arm
    accepted it, faceted.
  - **The keg** (on its side on a cradle) and **the mug** (a handle, a foam head) fall back to
    generic. All three are the false accepts.
- **The parts arm** carries what the generic arm broke:
  - the lantern, frame and ring in one piece (WI 2120: 50 pieces);
  - the post light.

  It fails where the source is one merged part with thin members: the iron gate, the candelabra, the
  hanging lantern, WI 2112's lantern. There it reduces to simplifying the whole prop, which loses or
  detaches the thin members.
- **The box arm accepted no prop in this set.**
  - **WI 2091's closed crate** missed narrowly: 5.8 % from rebuild to source, as the box bridges
    the latches and caps it stands off, and colour 5.0–5.2 % in two views. WI 2091 judged that
    bevelled box the cleanest by eye; the generic arm accepted the crate here. The 4 % and 5 % limits
    are the prototype chain's, not set for a fitted primitive.
  - **The others are not boxes:** the chest's lid is domed, the crate open-topped, the bookshelf a
    cabinet with feet and a cornice, the tombstone a stone on a base.
- **The generic arm,** with the voxel chosen by pieces and debris dropped, gives one piece for the
  Westfall fence (WI 2120: 24) and carries open frames: 6 of 8 hits.
- **The planar arm crashed on the rug.** Its coarse remesh (size/40) left an empty mesh, *Hypothesis*:
  the rug is 4 cm thick, under one voxel. The generic arm took it. Blender exits 0 on a script error
  unless told otherwise, so the stage now passes `--python-exit-code 1`. The run read the missing
  output as a failure either way.

## Refused props and their rows

| Prop | Arms tried: failing rows |
|---|---|
| 2112_lantern | parts: size; generic: size, colour |
| 2120_crate | box: shape, colour; generic: shape, colour |
| 2120_iron_gate | generic: colour; parts: size, colour |
| 2120_candelabra | generic: pieces, floating, shape, colour; parts: size, pieces, floating, shape, colour |
| 2120_hanging_lantern | parts: pieces, shape, colour; generic: pieces, floating, colour |
| 2120_bookshelf | box: shape, colour; generic: colour |
| 2120_utensils | parts: colour; generic: floating, colour |
| 2120_book_stack | parts: pieces, floating, shape, colour; generic: colour |
| 2120_tools | parts: pieces, shape, colour; generic: colour |
| 2120_hay_pile | generic: size, colour; parts: colour |
| 2120_cliff_rock | generic: triangles, shape, colour; parts: lods_decrease, size, shape, colour |
| 2120_tombstone | box: shape, colour; generic: size, colour |

## The control: the new rows over WI 2120's own outputs

The pieces, floating, shape and colour rows run with no rebuild over WI 2120's generic outputs
(`../stage/control_2120.py`). WI 2120's gate had passed all of these but the cliff rock.

| Prop | Source parts | Rebuild pieces | Floating | Shape p95 | Worst view | New rows |
|---|---|---|---|---|---|---|
| lantern | 1 | 13 | 42 | 2.6 % | 6.1 % | refuse |
| hanging_lantern | 1 | 9 | 29 | 2.0 % | 7.2 % | refuse |
| iron_gate | 1 | 6 | 6 | 2.5 % | 13.0 % | refuse |
| hay_pile | 1 | 51 | 67 | 3.5 % | 29.9 % | refuse |
| cliff_rock | 1 | 28 | 68 | 2.2 % | 9.4 % | refuse |
| candelabra | 1 | 6 | 10 | 2.1 % | 2.9 % | refuse |
| keg | 1 | 1 | 6 | 3.4 % | 4.1 % | refuse |
| barrel | 1 | 1 | 0 | 1.6 % | 1.9 % | accept |
| bottle | 1 | 1 | 0 | 1.6 % | 1.0 % | accept |
| elwynn_fence | 1 | 1 | 0 | 1.1 % | 1.6 % | accept |
| table | 1 | 1 | 0 | 1.4 % | 1.3 % | accept |
| chair | 1 | 1 | 0 | 1.2 % | 0.8 % | accept |
| rock | 1 | 1 | 0 | 1.3 % | 0.8 % | accept |

- **The rows refuse the five props whose look failed on loose or fragmented parts, and accept the six
  that held.** *Confirmed* on these 13.
- **A pieces row counting raw fragments would have passed three of them.** TRELLIS.2's sources come in
  up to 346 fragments: 346 on the hanging lantern, against its 30 rebuilt pieces.
- **The keg shows the merge's looseness:** one merged piece, yet six floating. The grid merges parts up
  to about 3.5 % apart, and the floating row catches the gaps.

## Measurement notes

- **The shape row is two-way.** Leaving out source points buried in a closed rebuild (WI 2120's
  `outside.py`) let a rebuild that encloses its source pass: a box around a sphere read 1.9 %. The
  rebuild-to-source direction reads it at 26.3 %.
- **The consumer's light:** Elwynn's keys from the pack (`sun` and `ambient` at 12:00 and 18:00, sRGB
  decoded as the client does), with the sun at 73° and 15°. Calibrated against WI 2091's in-game
  capture of its generic crate: with the sun on the cameras' side (azimuth 60°), the rig shows the
  notch and facets the game showed; at azimuth 160° it did not.
- **The tall categories' heights** come from the Elwynn pack's most-placed model of the kind:
  - bookshelf 4.22;
  - weapon rack 2.91;
  - post light 4.10;
  - candelabra 1.49;
  - tools 1.56;
  - iron gate 2.23.

  The two lanterns' heights (0.6 and 1.0) are guesses, since the pack's lanterns are other objects.
- **Time:** 14–50 s a prop, 821 s for all 33. The first arm's success is the fast path.

## For the next step

- **The colour row's view from above** refused two faithful props, and the debris rule shrank one past
  its size row. Both are row design, not rebuild failures:
  - weigh the view from above with the others, or give it its own limit;
  - let the debris rule keep pieces on the governing extent.
- **The round class needs the lathe to hold where a body carries a cradle or a handle** (the keg, the
  mug). The jar's 22 % is the case to diagnose first.
- **Thin members on a single-part source** (gates, candelabras, bracketed lanterns) need a route that
  keeps members: rods fitted as prisms, say. The parts arm cannot split what the generator welded.
- **The box arm wants its own limits and a closed-box test.** On WI 2091's crate it missed the 4 %
  and 5 % rows narrowly, and most of the set's "boxes" were not boxes.
