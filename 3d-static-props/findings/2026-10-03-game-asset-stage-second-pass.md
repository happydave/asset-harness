# Findings: the game-asset stage's second pass, re-scored on WIs 2112 and 2120's sets

**Date:** 2026-10-03 · **Work item:** WI 2143 (tickets) · **Host:** `ai2`, cores 12–23 (Blender
4.2.22 headless, trimesh 5.1.1, scipy 1.18.1, glTF-Validator 2.0.0-dev.3.10) · **The stage:**
[../stage/](../stage/README.md) · **Before:** [WI 2092's findings](2026-10-03-game-asset-stage.md)

**Provisional, twice, as WI 2092's run was.** The style is unanchored until WI 2093, and the licence is
the lane's `conditional` until WI 1749's O1 and O2. The sidecars carry the lane and provisional records
unchanged. Nothing here ships.

WI 2092's stage disagreed with the eye on 6 of WI 2120's 27 props. This pass looked at each wrong verdict
on the prop before changing a rule. Two of WI 2092's readings turned out wrong, and one planned arm was
built, tried and removed. The stage then ran once on the same 33 sources, consumer table and rig, and
every changed verdict was read by eye. Two of them, the bookshelf and the book stack, carry WI 2092's
reading of an identical rebuild. The set:
[samples-2026-10-03-game-asset-stage-second-pass/](samples-2026-10-03-game-asset-stage-second-pass/),
laid out as WI 2092's, with labelled sheets of each changed arm in `sheets/` and `look.json`. One reader,
the author.

## The re-score (WI 2120's 27)

| Class | Props | Accepted | Hold by look | Hits | WI 2092's hits |
|---|---|---|---|---|---|
| open frame | 8 | 6 | 6 | 6 | 6 |
| round | 5 | 5 | 3 | 3 | 2 |
| box | 4 | 3 | 3 | 3 | 2 |
| cluster | 3 | 1 | 1 | 1 | 0 |
| organic | 3 | 1 | 1 | 1 | 1 |
| small detailed | 2 | 1 | 1 | 1 | 1 |
| flat | 1 | 1 | 1 | 1 | 1 |
| slab | 1 | 0 | 1 | 0 | 0 |
| **all** | **27** | **18** | **17** | **16** | **13** |

"Hold by look" is read on the arm the stage accepted, or on its best attempt when it refused. The mug
holds now because its lathe holds; its generic rebuild did not.

**The gate and the look agree on 24 of 27; WI 2092's agreed on 21.**
- **Fixed, three:**
  - the mug, a false accept, is now a hit by the lathe;
  - the bookshelf and the book stack, false refusals, are now hits by the generic arm. Their rebuilds
    are identical to WI 2092's, value for value, and only the colour row changed.
- **Still wrong, three:**
  - **The jar, a false accept.** Its lathe now fits (3.05 % against 22 %), but the bake of its hollow
    leaves a dark scalloped band and a torn shoulder. The colour row refuses it (8–9 %), rightly, and
    the generic arm accepts it faceted.
  - **The keg, a false accept.** Its body does not lathe: its largest residual is 26 % of its area. The
    lathe is refused on shape, floating and colour, and the generic arm accepts it faceted.
  - **The tombstone, a false refusal.** Its cause was not the one WI 2092 named (below).

**If the round class drops its generic arm** (the plan's open question for the owner), the jar and the
keg are refused instead. Agreement rises to 26 of 27, with no false accepts and the same 16 hits. The
generic arm has made no round hit in either run.

**WI 2112's six:** 6 of 6 agree, as before. WI 2091's crate is now accepted by the box arm (below), and
the lantern is still refused.

*Supported*: one run a prop, one reader. The stage is deterministic at these settings. The five generic
rebuilds compared value by value (the bookshelf, the book stack, the tombstone, the jar, the keg) match
WI 2092's exactly. Time: 14–52 s a prop, 847 s for all 33
(WI 2092: 821 s).

## What changed, and why

### The colour row's view from above

The front, side and back views keep 5 %. The view from above (elevation 55°) gets 8 %, since it sees
top faces and shelf interiors at a slant and in play the camera stands near a prop's side.
- On WI 2092's values, no arm whose look fails becomes accepted by this.
- One becomes colour-clean, the candelabra's generic arm (above 7.42 %), but it stays refused on
  pieces, floating and shape.

### The tombstone: the remesh, not the debris rule

WI 2092 read the tombstone as shrunk by the debris rule. A copy of the stage that logs every island shows
otherwise:
- the three islands dropped are two-face crumbs in mid-air, inside the main piece's span;
- the main piece itself is short (0.692 against 0.8), because the voxel remesh lost the thin dirt ground
  patch, the prop's widest part;
- no divisor met the source's one part, so the ladder ended at its coarsest step (size/48);
- the missing brown patch also explains the colour row failing in every view (5.5–8.8 %).

The debris rule is unchanged. The voxel ladder is unchanged too, since changing it changes every generic
prop. A remesh that keeps thin ground patches is open.

### The lathe: open vessels and the body's own axis

- **An open vessel.** Seen from above, the highest point inside the jar's mouth is its inside floor. The
  top cap therefore ran from the rim straight down to the floor, a cone through the hollow belly (22 %
  off at p95). Where the cap drops more than a quarter of the height inside the rim, the profile now
  runs over the rim and down the inner wall to the floor. The jar's lathe: 3.05 %.
- **The axis.** The lathe's axis ran through the bounding box's centre, which a handle (the mug, 6.4 %
  of the size) or a cradle (the keg, 4.5 %) pulls off the body's axis. It now runs through circles
  fitted to the body's cross-sections, refitted without the attachment's points.
  - The "residual parts" WI 2092 blamed on the mug's handle and the keg's cradle were whole sides of an
    off-centre body.
  - The barrels, the bottle and the jar shift by 0.0001 of the size or less.

The residuals stay as WI 2092 built them. Closed solids (a box, a prism, a hull) were tried for each
residual cluster of the six round props, and none fitted one within 4 %. Each cluster's own
simplification fitted it within 3 % on the barrels, the bottle and the mug, and on the jar's larger
cluster. The jar's second cluster missed by 20.6 % and the keg's largest by 25.8 %, yet the jar's arm
as a whole measures 3.05 %, so the gate, not a per-cluster rule, judges.

### The shape row: buried surfaces per closed piece

The shape row leaves out source points buried more than 2 % inside the rebuild, since TRELLIS.2 leaves
surfaces where parts meet and inside bodies. It did so only when the whole rebuild was closed, and a
lathe body with an open residual band is not. The mug's inner cup, 54 % of its source's samples,
counted as 9.7 % off. Now a point is buried inside any closed piece of the rebuild, and the mug reads
1.9 % forward.
- trimesh's `split` fills holes by default, which closed an open piece in a test. The row splits
  without repair.
- A source wholly enclosed by its rebuild once raised an error. Its forward distance now reads 0, and
  the backward direction refuses it.

### The box arm: a fitted box and its own shape limit

WI 2091's crate stands off a box on every face: its panels sit about 4 % inside its frame boards (median
standoff 3.7–3.9 % on the sides, 5.6 % underneath).
- **No axis-aligned box fits it within 4 %.** Trimming faces inward past up to 5 % of the surface samples moved the
  best fit only from 6.27 % to 5.72 %.
- **The fitted box:** the box now takes the trim with the best two-way fit, never shortening the
  governing axis by more than 2.5 %. That sits it closer to the body, and the bake improves: the
  crate's colour falls from 5.03–5.21 % to 4.25–4.99 %.
- **Its own shape limit of 6 %:** the crate's 5.73 % rounded up to the next half percent.
  - The box-arm refusals that must hold by shape still hold: the chest's domed lid at 11.8 %, the
    planter at 8.4 %, WI 2120's open crate at 16.6 %, the tombstone at 27.9 %.
  - The bookshelf's box passes shape (5.23 %) and is refused by colour.

**WI 2091's crate passes the box arm, and holds by look** under even light and the consumer's light. Its
margins are thin: the back view's colour is 4.99 % against 5 %, and the shape 5.73 % against 6 %.

### A members arm, built, tried and removed

Thin members on a source the generator welded into one part (the iron gate, the candelabra, the hanging
lantern) were to be kept as rods. The arm was built:
- a filled voxel grid;
- thin regions at 6 % of the size, a threshold measured on the props;
- straight runs found greedily, each a box on its principal axes.

On the gate's shape measure it reached 3.1–3.5 %. But with a 300-triangle budget, 25 boxes cover either
a gate's bars or its rails and frame, not both, and the boxes did not join into one piece. Through the
whole stage it was refused on all four props it was tried on, colour among the failing rows each time
(9–18 %). By eye the lantern became a tangle of crossed boxes, and the gate a row of planks between
posts built of runs. The plan's rule was that its look decides, so it was removed. Thin members at this
budget are an open problem.

Two defects it exposed in shared code are fixed: the lathe's revolve now takes a profile with two axis
points in a row, and one wholly on the axis.

## Refused props and their rows

| Prop | Arms tried: failing rows |
|---|---|
| 2112_lantern | parts: size; generic: size, colour |
| 2120_candelabra | generic: pieces, floating, shape; parts: size, pieces, floating, shape, colour |
| 2120_cliff_rock | generic: triangles, shape, colour; parts: lods_decrease, size, shape, colour |
| 2120_crate | box: shape, colour; generic: shape, colour |
| 2120_hanging_lantern | parts: pieces, shape, colour; generic: pieces, floating, colour |
| 2120_hay_pile | generic: size, colour; parts: colour |
| 2120_iron_gate | generic: colour; parts: size, colour |
| 2120_tombstone | box: shape, colour; generic: size, colour |
| 2120_tools | parts: pieces, shape, colour; generic: colour |
| 2120_utensils | parts: colour; generic: floating |

Every one of these fails by look as well, except the tombstone.

## For the next step

- **The owner's question:** should the round class drop its generic arm? On both runs it made no round
  hit, and here it makes the only two false accepts.
- **The jar's bake.** The lathe now has the right shape, but the bake of its inner wall and belly goes
  wrong. The cause is a hypothesis: rays cast from an inner surface reach the outer one.
- **Thin ground patches lost by the remesh** (the tombstone): a ladder step finer than size/96 near the
  ground, or a planar treatment of a base, would be needed.
- **Thin members at a 300-triangle budget:** rods from voxels did not carry them. A plane with the bars
  in an alpha-tested texture is a *hypothesis* worth a spike.
