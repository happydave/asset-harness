# Findings: rigid robot walk (Direction A, Prototype A)

**Date:** 2026-07-09
**Track:** rigged-avatars
**Verdict:** works

## Goal

Prove **Direction A** of the rigged-avatars track (WI 882): a rigged, rigid-humanoid "robot" avatar
built with **no AI in the loop** — parametric Blender geometry + a standard humanoid armature + each
rigid part object-parented to one bone + hand-keyed idle/walk clips, exported to glTF for the games
(Sounding first). Target the "a little janky, even goofy" bar. For all three games via the
engine-agnostic glTF output.

## Tooling

- **Base model:** none — **no AI** (that is the point of Direction A).
- **LoRA(s) / ControlNet / adapters:** none.
- **Workflow / nodes:** [`prototypes/blender_robot.py`](../prototypes/blender_robot.py) (generator:
  geometry + armature + rigid bone-parent + animation + glTF export + rich `robot_manifest.json`),
  [`prototypes/bake_glb_extras.py`](../prototypes/bake_glb_extras.py) (pure-python: injects
  per-animation + root `extras` into the glb from the manifest), and
  [`prototypes/render_robot_preview.py`](../prototypes/render_robot_preview.py) (imports the exported
  `.glb` and renders a walk contact-sheet — also validates the round-trip).
- **Other software:** Blender 4.0.2 headless on `ai2` (same pattern as `mechanical-kit`); the baker
  runs anywhere python3 does (no Blender, no deps).

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Blender (tool) | GPL | yes | yes | outputs are **yours**; GPL does not touch generated assets |
| Authored geometry (bpy primitives) | ours | yes | yes | this repo |
| Hand-keyed motion (idle/walk) | ours | yes | yes | authored by hand — **not** from AMASS/Mixamo/text-to-motion |

- **Effective output license:** fully clean / commercially redistributable.
- **Safe for a clean/commercial asset pack?** **Yes.** This is the whole reason Direction A is the
  preferred path: it never touches the poisoned motion corpora or NC mesh-gen dependencies the
  discovery flagged.
- **Notes:** no attribution obligation (unlike the Meshy-free path in Direction B).

## Hardware

- **Machine / GPU:** `ai2` (gfx1201 R9700), Blender 4.0.2, EEVEE for preview.
- **Stack:** ROCm host. Note: no CUDA/mesh-gen models involved, so the ROCm "out for local mesh-gen"
  constraint (see discover.md) does **not** apply to Direction A — this pipeline runs anywhere Blender
  runs.

## Inputs

- **Prompt(s) / Seed(s):** none — fully parametric/deterministic.
- **Key params:** ~1.8 m biped; 22 parts; 19-bone humanoid armature; walk = 24-frame loop (keys at
  1/7/13/19/25), thigh swing 0.45 rad, arm swing 0.35 rad, knee bend to 0.95 rad on lift, hip bob
  0.03 m, slight forward lean; idle = 48-frame breathing bob + head turn.

## Steps

1. `scp prototypes/*.py ai2:/tmp/`
2. `ssh ai2 'cd /tmp && blender --background --python blender_robot.py -- --out /tmp/robot_out'`
3. `ssh ai2 'cd /tmp && blender --background --python render_robot_preview.py -- --glb /tmp/robot_out/robot.glb --out /tmp/robot_out'`
4. `scp -r ai2:/tmp/robot_out/* prototypes/out/`
5. `python3 prototypes/bake_glb_extras.py --dir prototypes/out`  (inject glb extras from the manifest)

## Result

- **Sample output(s):** [`prototypes/out/robot.glb`](../prototypes/out/robot.glb) (120 KB),
  `prototypes/out/debug/robot.gltf`(+`.bin`), `prototypes/out/robot_manifest.json`, and the walk
  contact-sheet `prototypes/out/robot_walk_00..07.png`.
- **glTF structure (verified by parsing the GLB JSON):** 42 nodes, 22 meshes, **1 skin (skeleton
  joints only)**, **2 animations `idle` + `walk`** (each 57 channels = translation+rotation+scale on
  all 19 bones). Crucially: **22 mesh-bearing nodes, 0 of them skinned** → the rigid-bind invariant
  holds — parts are plain child nodes of their joint nodes, animated by joint TRS, **zero
  deformation**. Clip names in the glb are clean (`idle`/`walk`).
- **Round-trip:** re-importing `robot.glb` recovered the `walk` clip (range 1–25) and rendered — the
  animation survives the glTF round-trip (re-checked after the extras bake: still loads + animates;
  GLB chunks stay 4-aligned, BIN preserved verbatim).

### Clip metadata — glb `extras` + sidecar (added 2026-07-09)

Two consumers, one source of truth (`clip_meta()` in the generator → `robot_manifest.json`):

- **Sidecar `robot_manifest.json`** — authoritative, engine-friendly. `clips` is now a rich map:
  per clip `{loop, fps, frame_start, frame_end, nominal_duration_s, events[]}`. Load it beside the
  glb and key clips by name. This is what game code should read (no dependency on whether an engine
  surfaces animation `extras`).
- **Embedded glb `extras`** (via `bake_glb_extras.py`) — the travels-with-the-asset mirror for
  glTF-aware tooling (viewers, GLB Studio, DCC round-trips). Injects onto **each animation**
  `{loop, fps, frameStart, frameEnd, durationSec, events[]}` and a **root** `extras.asset_harness`
  provenance block (generator, license, frame, bind).
- **Foot-event schedule** (walk): `foot_plant`/`foot_lift` for L/R at the contact/toe-off frames
  (50% duty) — the frames a downstream procedural-IK gait locks/releases the foot. Each event carries
  `frame`, normalized `phase` (0..1), and an exact `timeSec` **on the clip's own time axis**.
- **Convention lesson (important):** Blender's glTF exporter writes keyframe times as `frame/fps`, so
  the walk's frame 1 is at **0.0417 s**, not 0, and `durationSec = 25/24 = 1.04167 s` (not 1.0). So
  **absolute seconds must be read from the glb, never recomputed from `fps`.** The fix: author events
  by `frame`+`phase` (convention-independent) and let the baker resolve `timeSec` from the sampler's
  own min/max accessor times — the events then land exactly on the engine's keyframe axis.
- **What worked:**
  - **Rigid bone-parent → clean node hierarchy.** Object-parenting each part to one bone (via
    setting `parent_type='BONE'` + restoring `matrix_world` to avoid a jump) exports exactly as the
    research predicted: no `SkinnedMesh`, no weights, TRS-animated joint nodes. This is the
    simplest-to-import, cleanest-licensed rig.
  - **`export_animation_mode='ACTIONS'`** with `use_fake_user=True` on each action gave two named,
    separate glTF clips from one file.
  - Reads unmistakably as a friendly, slightly-goofy bipedal robot (antenna + cyan visor eyes); the
    contact→passing→opposite-contact cycle reads as a walk.
- **What failed / artifacts (all acceptable for the brief):**
  - `EGL_NOT_INITIALIZED` warning on the headless EEVEE render — **harmless**, frames still wrote.
  - Draco library missing — **harmless / wanted**: uncompressed glTF is what Bevy expects.
  - Gait jank: stride is wide, feet stay rigid (no heel/toe plant-roll, so a foot floats a touch at
    contact). On-brand ("a little janky/goofy"); the real fix is the downstream **procedural-IK gait**,
    not more hand-keying (see Next).
  - **Knee direction (fixed 2026-07-09).** The first pass bent the knee the wrong way (a reverse/bird
    knee — the foot kicked *forward* on the bend). Fixed by negating the `shin` `rot_x`. **Rigging
    lesson:** for a *downward-pointing* limb bone, `+rot_x` swings the tail (foot) **forward** →
    reverse knee; `−rot_x` tucks the calf **backward** → human knee. Same fix applied to the
    corn-person (WI 885).
  - First pass had near-black limbs (poor legibility) → lightened the limb material; second pass reads
    clearly.

## Repeatability

Fully deterministic (no seed, no AI, no sampling). Re-runnable headless on `ai2` with the documented
command; geometry and motion are identical every run.

## Next

- **Downstream (Sounding repo, deferred — out of scope here):** feed `robot.glb` into a Bevy scene
  and drive a **procedural two-bone-IK gait in Rust** (`bevy_animation_graph`), per the discovery
  recommendation (baked walk was to prove the rig; IK is the real locomotion). Ties to Sounding
  WI 561. **Record for that step:** Bevy spawns the `AnimationPlayer` on a glTF *descendant* (walk
  `iter_descendants`, not `single_mut()`); export is already +Y-up / metres / scale-applied.
- **Optional polish (this track):** foot heel/toe plant-roll; a rigid-part hand with a couple of
  finger segments; NPC-variety parameterization (proportions/colours from a seed).
- **Prototype B** (Kerbal-tier stylized + corn→popcorn failure-transform) is the next track item.
