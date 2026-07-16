# Track: rigged-avatars

**Status:** 🟡 **Prototypes A + B work** (2026-07-09) — both clean-licensed, no AI. **A** (WI 882):
rigid robot walks ([findings](findings/2026-07-09-rigid-robot-walk.md)). **B** (WI 885): Kerbal-tier
corn-person + **corn→popcorn failure transform** ([findings](findings/2026-07-09-corn-person-popcorn.md)).
Discovery complete 2026-07-08 ([discover.md](discover.md)). [visual/manual] owner sign-off pending on
both; AI-mesh comparison (Meshy→UniRig) is an owner-run recipe in the B findings.

**VRM export (WI 925, 2026-07-14):** the corn-person now also exports **VRM 1.0 + 0.x** via
`blender_corn.py --vrm` — 19-bone humanoid map (no re-rig), clean-lane meta, a husk-tuft spring chain,
game-lane `.glb` kept (VRMs drop clips by convention). The reusable exporter is
[`prototypes/vrm_export.py`](prototypes/vrm_export.py); [findings](findings/2026-07-14-corn-vrm.md).
Needs Blender 4.2+ with the saturday06 VRM add-on (on ai2: `~/blender-4.2/blender`, WI 933). [visual/manual]
three-vrm browser load pending. This is the VTuber ladder's walking skeleton — it de-risks the export chain
before the WI 926 skinned + shape-key kill-shot.

**MPFB2 body-donor eval (WI 927, 2026-07-15) — qualified:** timeboxed evaluation of **MPFB2** (MakeHuman's
Blender add-on) as a **CC0 skinned-body donor**. Verdict: **no for the current Kerbal-tier stylized
direction** (a primitive-authored body is cheaper *and* a better aesthetic fit; MPFB's realistic 13.4k-quad
mesh would fight the blocky look), **qualified yes as a reserve donor** for any future realistic/semi-realistic
avatar (e.g. deferred WI 930). Every hard gate passed — scripted headless generation works, topology is
production-grade **pure-quad**, the **`game_engine` 53-bone rig maps 1:1 onto our 19-bone VRM humanoid**, and
the **CC0 asset licence is clean** (verified from `LICENSE.md`/`LICENSE.ASSETS.md`; §D disclaims scripted
output; the MakeHuman-standalone automation carve-out — a trap — does **not** apply to MPFB2). Body only:
MPFB2 has **no ARKit shape keys** (bone-based face, WI 923), so face morphs stay ours (WI 936). Harness:
[`prototypes/mpfb2_body_eval.py`](prototypes/mpfb2_body_eval.py); [findings](findings/2026-07-15-mpfb2-body-donor.md).
MPFB2 v2.0.17 installed as a Blender extension on ai2.

**Stylized expressive head (WI 936, 2026-07-15):** [`blender_expressive_head.py`](prototypes/blender_expressive_head.py)
— the first cut of the **stylized head archetype** (WI 923 ladder step 5) and a proper expressive demo for
the Studio VRM inspector. A skinned Kerbal-tier head with **14 authored ARKit morphs** (blinks, eye
wide/squint, brows, jaw, smile/frown) and the **full ARKit-52 declared** (14 bound + 38 empty Perfect-Sync
stubs); eyes/brows/mouth are material regions on the single deformable mesh so the morphs read. VRM 1.0 + 0.x
+ glb via `vrm_export.py`; 14/14 automated + readable by preview render. [findings](findings/2026-07-15-expressive-head.md).
[visual/manual] load in the Studio inspector.

**Kill-shot spike (WI 926, 2026-07-14) — PASSED:** a **skinned** mesh (armature modifier + weights, not
bone-parenting) carrying **four ARKit-named shape keys** (`eyeBlinkLeft/Right`, `jawOpen`, `mouthSmileLeft`)
survives headless Blender → **VRM 1.0 + 0.x** with skin, morph targets, morph names, and expression binds all
intact and re-importable (18/18 automated checks). **The VTuber approach is not dead; the ladder can
proceed.** Second question answered: **VRM export drops glTF animation clips** (both VRMs `animations=0`, the
`.glb` keeps its clip) → the game lane needs its own `.glb`, VRM + `.glb` are two artifacts from one source
scene. Generator [`prototypes/blender_face_spike.py`](prototypes/blender_face_spike.py); the shared
[`vrm_export.py`](prototypes/vrm_export.py) now carries skinning + morph-expression binding (raw ARKit 1:1
customs + composed presets), inherited by the real head (WI 923 step 5). [findings](findings/2026-07-14-face-spike.md);
[visual/manual] three-vrm drive-each-expression pending.

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
