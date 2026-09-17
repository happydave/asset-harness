# Findings: spring bones — hair chains and a head collider

**Date:** 2026-09-17
**Track:** rigged-avatars
**Verdict:** works — three hair chains and a head collider in both VRM 1.0 and 0.x, with the runtime behaviour measured headlessly

## Goal

[WI 923](../discover.md) **VTuber ladder step 10**: secondary motion for the stylized avatar, and the two
follow-ups [WI 925](2026-07-14-corn-vrm.md) deferred — F1, the head collider the exporter silently dropped,
and F2, the VRM 0.x spring it never wrote. asset-harness WI 1366.

## Tooling

- Blender 4.2.22 LTS + saturday06 VRM add-on v4.4.0 on ai2, as `notdave` (WI 1524). The add-on's spring API
  was probed live and then exercised in a throwaway export before anything was planned on it.
- [`prototypes/vrm_export.py`](../prototypes/vrm_export.py) gained `export_vrm(springs=…)`;
  [`prototypes/blender_v1_face_rig.py`](../prototypes/blender_v1_face_rig.py) gained the hair;
  [`prototypes/arkit52.py`](../prototypes/arkit52.py) gained `ARCHETYPE_SPRINGS`;
  [`prototypes/vrm_gate/`](../prototypes/vrm_gate/README.md) gained the spring rows and the simulation.
- three-vrm 3.5.5 in headless Chromium runs the simulation. Nothing installed.

## Licensing (commercial / redistribution)

Authored geometry and configuration only; no model, no donor asset. Effective output licence unchanged: clean.

## What was built

- **Hair, as a placeholder shape.** Two side tails of three segments hanging from ear height at x = ±178 mm —
  outside the head's 160 mm x semi-axis, so a sideways head roll drives one into the head, which is the case
  the collider exists for — and a two-segment lock rising from the crown. One mesh object, `hair`, 88
  vertices, each weighted 1.0 to one hair bone; the bones are added after auto-weighting, so the face mesh
  and its 29 morphs are untouched (the gate's displacement figures are unchanged). How hair *looks* is the
  toon lane's job.
- **One springs table, two writers.** Colliders, collider groups and chains are declared once and written to
  `VRMC_springBone` and to 0.x `secondaryAnimation`. Both files carry three chains, `center` on the hips, and
  one 160 mm sphere collider on the head bone at the head's centre.

## What the add-on and the runtime turned out to do

- **Colliders must be created by the add-on's operators** — WI 925's F1 cause, confirmed, and the remedy works
  in both specs.
- **The two specs place a sphere differently.** The 1.0 `sphere.offset` property is written to the file
  verbatim, so it is already in the glTF node frame: Blender `(dx, dy, dz)` from the bone head is `(dx, dz,
  -dy)`. The 0.x collider *is* an Empty; its radius is its display size, and left where the operator puts it,
  it exports at the bone's **tail** — 30 cm above the head bone on this rig. It is placed by world matrix.
- **The exporter's own purge would have deleted the colliders**: `_purge_non_avatar` removed everything that
  was not the armature or one of its meshes, and a collider is an Empty. Caught by reading it before the first
  run.
- **A VRM 1.0 chain needs an end marker.** three-vrm builds n−1 spring joints from n listed joints — joint k
  swings toward joint k+1 — so the last hair segment never bent until each chain got a short, meshless end
  bone. Measured: 5 spring joints before, 8 after.
- **`center` does what the discovery said, and the choice of bone matters.** Measured tip movement relative
  to the head:

  | | `center` = hips | `center` = head | no `center` |
  |---|---|---|---|
  | head turns 35° | 49–92 mm | **0.0–0.3 mm** | 49–92 mm |
  | avatar moves 3 m, eased | 0.0–0.3 mm | 0.0–0.3 mm | **181–305 mm** |

  With the head as centre the hair is carried rigidly through a head turn — no sway at all, which is the
  feature. WI 925 used `head` for the corn's short upward tuft, where it matters little. The hips cancel whole-avatar translation
  just as well and leave the sway.
- **The collider works:** rolling the head 55° onto a shoulder leaves the nearest joint 1.4 mm inside the
  collider surface (hit radius included) with the collider, and 29.0 mm inside without it.
- **Not explained:** with any centre set, an *instant* stop from 15 m/s throws a chain to its exact antipode,
  where it stayed for the 27 steps observed. An eased stop over the same 3 m does not do it, and neither does
  a small move with an instant stop. The gate uses the eased move; the cause was not chased.

## Results

Generator on ai2: **105/105** (was 90). Gate on the fresh pair: **282 passed, 0 failed**, exit 0. Gate tests:
63. `blender_corn.py --vrm` output is unchanged by the exporter edits — both files' JSON compares equal
before and after.

Defects seen to fail at their rows: four through the real exporter (`no-collider`, `center-head`,
`no-center`, `collider-blender-frame`), five file edits (`drop-center`, `drop-collider-group`, `joint-order`,
`center-head`, `collider-transposed`), two edits to a 0.x file (a changed stiffness, a moved collider), and
seven breaks to the gate's own code.

One limit worth knowing: the roll row measures clearance from the collider the file *declares*. A misplaced
collider keeps it green (+8.4 mm) while the hair would be inside the real head. The eye-containment row is
what catches a misplaced collider.

## Open

`[human]` **See the hair move.** The simulation is runtime-side, so this is judged in a consumer: drop
`samples-2026-09-17-spring-bones/v1_face_rig.vrm` on the asset-studio inspector, or point
`prototypes/obs_page/` at it and move your head.

## Samples

[`samples-2026-09-17-spring-bones/`](samples-2026-09-17-spring-bones/) — the VRM 1.0 file (now the gate's
test fixture), manifest, evidence JSON, contact sheet and gate report.
