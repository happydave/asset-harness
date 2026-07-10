# Track: rigged-avatars

**Status:** 🟡 **Prototypes A + B work** (2026-07-09) — both clean-licensed, no AI. **A** (WI 882):
rigid robot walks ([findings](findings/2026-07-09-rigid-robot-walk.md)). **B** (WI 885): Kerbal-tier
corn-person + **corn→popcorn failure transform** ([findings](findings/2026-07-09-corn-person-popcorn.md)).
Discovery complete 2026-07-08 ([discover.md](discover.md)). [visual/manual] owner sign-off pending on
both; AI-mesh comparison (Meshy→UniRig) is an owner-run recipe in the B findings.

## Purpose

Rigged, animated characters (Sounding player/NPC avatar). The **weakest fit** for AI generation —
deferred until the earlier tracks proved the harness shape, now opened for exploratory discovery
(crew is not gating any game, so this is free exploration).

## Directions (both prototyped)

Two concrete directions, scoped in [discover.md](discover.md), both built via the Blender-primitives
path (no AI, cleanest license):

- **A — Rigid robotic humanoid** (WI 882, **works**): a biped built as an articulated rigid
  part-hierarchy (no skinned deformation) — parametric Blender + hand-authored armature + baked
  idle/walk. Ties to Sounding WI 561.
- **B — Stylized humanoid (Kerbal-tier)** with a **failure-state transform** (WI 885, **works**):
  a corn-cob person that **pops into popcorn** — the live rigged avatar + a `popcorn_burst` asset
  linked by metadata; the engine swaps one for the other on the failure event. Reuses the A rig
  verbatim. Other concepts (badger, tuber→mash, mushroom→spores, …) are new geometry on the same
  pipeline.

The **failure-transform** is a reusable mechanic: two clean assets (avatar + burst) linked by a
`failure_transform` in the avatar's metadata/`extras`.

## Approach (validated by discovery)

- **A (robot):** no AI in the mesh path — parametric Blender geometry + parts object-parented to an
  armature + **procedural two-bone-IK gait in Rust** (`bevy_animation_graph`). Cleanest license, no
  vendor, ties to Sounding WI 561.
- **B (stylized):** one honest AI attempt — `Meshy free (CC BY 4.0) → UniRig (MIT, local) → own
  animation` — with a hard fallback to a primitive-built Blender Kerbal-tier body if meshes fuse.
- **Licensing gate (confirmed):** the dirty link is **motion data**, not the mesh — **text-to-motion
  is poisoned** (AMASS non-commercial) and **nvdiffrast** (NC) sits under the AI texture stages.
  Never redistribute Mixamo/Meshy/ActorCore animation clips (ship-in-game only); own or procedurally
  generate motion.

## Contents

- [`discover.md`](discover.md) — completed scoping + findings/assessment (tool landscape + licensing).
- `prototypes/`:
  - [`blender_robot.py`](prototypes/blender_robot.py) — Prototype A generator (robot: geometry +
    armature + rigid bone-parent + idle/walk + glTF export).
  - [`blender_corn.py`](prototypes/blender_corn.py) — Prototype B generator (corn-person + popcorn
    burst; reuses the A rig).
  - [`bake_glb_extras.py`](prototypes/bake_glb_extras.py) — pure-python: bakes per-clip + root
    `extras` into a glb from its manifest (`--name`, `--merge <clip>`).
  - [`render_clip.py`](prototypes/render_clip.py) / [`render_robot_preview.py`](prototypes/render_robot_preview.py)
    — glb round-trip preview renders.
  - `out/` — `robot.glb`, `corn.glb`, `popcorn_burst.glb` (+ debug gltf + manifests + contact-sheets).
- `findings/` — [rigid robot walk](findings/2026-07-09-rigid-robot-walk.md) (A),
  [corn-person + popcorn](findings/2026-07-09-corn-person-popcorn.md) (B).
