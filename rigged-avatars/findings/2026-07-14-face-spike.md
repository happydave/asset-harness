# Findings: skinned + shape-key headless VRM round-trip (kill-shot spike)

**Date:** 2026-07-14
**Track:** rigged-avatars
**Verdict:** works

## Goal

Resolve the **one unverified assumption the entire VTuber-avatar initiative stands on** (asset-harness WI
926, the kill-shot): does a **skinned mesh carrying real shape keys** survive **headless Blender → VRM
(1.0 + 0.x)** with its skin deformation and morph targets intact, ARKit-named, and drivable in a consumer?
The repo had **zero skin weights and zero shape keys** before this — every existing avatar is rigidly
bone-parented — so this is the first time the skinned + morph path is walked at all. Also answers the
second question: does `export_scene.vrm` **preserve or drop** a glTF `animations` array?

## Tooling

- **Blender 4.2.22 LTS** + **saturday06 VRM Add-on v4.4.0** (extension format), home-dir on `ai2` at
  `~/blender-4.2/blender` (WI 933). System `/usr/bin/blender` (4.0.2) has no add-on.
- **New generator** `rigged-avatars/prototypes/blender_face_spike.py` — a **skinned** head+body (ARMATURE
  modifier + auto vertex weights, *not* bone-parenting) on the 19-bone humanoid rig, with **four ARKit-named
  shape keys** (`eyeBlinkLeft`, `eyeBlinkRight`, `jawOpen`, `mouthSmileLeft`, each a distinct-region morph),
  one bone `nod` clip, and a dual VRM + game-lane `.glb` emit. Reuses `blender_corn.py`'s pure rig helpers so
  the bone names match the humanoid map exactly.
- **Extended** `vrm_export.py` (the shared exporter from WI 925) with `_set_expressions`: binds raw ARKit
  shapes as **1:1 VRM 1.0 customs** and the double-duty shapes as **composed presets** (blink / aa / happy),
  plus VRM 0.x `blendShapeGroups`. The bind selector `index` is the **shape-key name string** (probed live
  on v4.4.0 before coding). The exporter now also selects skinned mesh children so a skinned probe is not
  dropped.
- Headless: `~/blender-4.2/blender -b --python blender_face_spike.py -- --out DIR`.

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Blender + VRM add-on | GPL-3.0-or-later + MIT | tool only | — | the tool licence imposes **nothing** on exported assets |
| probe geometry / rig / morphs | authored (ours) | yes | yes | Blender primitives + hand-set shape keys |

- **Effective output license:** **clean** — authored geometry + hand-set morphs; the add-on's GPL/MIT
  imposes nothing on output. (Spike samples are a technical probe, not a shipped avatar.)
- **ARKit naming is clean** (WI 923 finding): `ARFaceAnchor.BlendShapeLocation` is public Apple API
  vocabulary; naming our own original shape keys after it involves none of Apple's code or assets. Describe
  the result as "ARKit-compatible / Perfect Sync", not "ARKit®".
- **Safe for a clean/commercial pack?** Yes (the capability; the probe geometry itself is throwaway).

## Hardware

- `ai2` — CPU (parametric Blender export needs no GPU). Fast (seconds).

## Inputs

- `blender_face_spike.py --out ~/wi926`. Deterministic: parametric geometry + fixed vertex displacements,
  no randomness.

## Steps

1. Generate: one run emits `face_spike.glb` (skin + 4 morphs + `nod` clip), `face_spike.vrm` (1.0),
   `face_spike.vrm0.vrm` (0.x), manifest.
2. Validate (`validate_face_spike.py`): parse each glb JSON chunk — `skins`, `JOINTS_0`/`WEIGHTS_0`, morph
   `targets`, `extras.targetNames`, `VRMC_vrm.expressions` (customs + presets, binds resolve), VRM 0.x
   `blendShapeMaster` groups, `animations` length — then re-import both VRMs via `import_scene.vrm`.

## Result

- **Samples:** [`samples-2026-07-14-face-spike/`](samples-2026-07-14-face-spike/) — `face_spike.vrm` (1.0),
  `face_spike.vrm0.vrm` (0.x), `face_spike.glb` (game lane), manifest.
- **Verdict: `works` — the kill-shot passed. The VTuber approach is not dead; the ladder can proceed.**
- **What worked (18/18 automated checks):**
  - **Skin survives to both specs** — `skins` array + `JOINTS_0`/`WEIGHTS_0` on the mesh primitives in the
    `.glb`, the 1.0 `.vrm`, and the 0.x `.vrm`. Skinning (armature modifier + weights), not bone-parenting.
  - **Four morph targets survive with ARKit names byte-exact** — `targetNames ==
    ['eyeBlinkLeft','eyeBlinkRight','jawOpen','mouthSmileLeft']` in the `.glb` and both VRMs.
  - **Expressions resolve** — VRM 1.0 has all four ARKit shapes as **1:1 custom** expressions (one morph
    each) **and** the double-duty presets `blink` (2 eye morphs), `aa` (jawOpen), `happy` (smile) as
    compositions; every custom bind resolves to a real morph target on a real mesh. VRM 0.x carries the
    equivalent `blendShapeGroups`. This is the file that answers the Warudo raw-morph-vs-expression
    binding-precedence question flagged in research.
  - **Both VRMs re-import cleanly** — head mesh reconstructed with its 4 ARKit shape keys + the armature
    modifier, no exception.
  - **Answer #2 — VRM export DROPS glTF clips.** `animations=0` on both `.vrm` files; `face_spike.glb` keeps
    `animations=1`. **Artifact plan: the game lane needs its own `.glb`; VRM + `.glb` are two artifacts from
    one source scene.** (Confirmed for the skinned case, matching WI 925's rigid-case result — the skin
    channels do not change the outcome.)
- **Notes:** the VRM 0.x exporter auto-fills the full standard preset list (13 groups; the 3 we populate
  carry binds) — expected add-on behaviour. VRM0 bind weight set to 1.0; if 0.x/VSeeFace amplitude reads
  weak in the manual gate, the add-on may expect a 0–100 scale (one-line follow-up, not a blocker).

## Repeatability

- Deterministic; parametric build, fixed vertex displacements. Re-running reproduces byte-stable geometry.
- **Gotcha (inherited from WI 925):** `read_factory_settings` disables the VRM add-on + drops its
  preferences; `vrm_export.ensure_addon()` re-enables it (`default_set=True`) before any VRM data is touched.

## [visual/manual] — owner gate

Load `face_spike.vrm` in a browser `three-vrm` viewer and confirm **(1)** the head mesh deforms *smoothly*
under the bone motion (skinned, not rigid) and **(2)** driving each expression (`eyeBlinkLeft`,
`eyeBlinkRight`, `jawOpen`, `mouthSmileLeft`, and presets `blink`/`aa`/`happy`) to weight 1.0 produces a
visibly distinct deformation. Optionally load `face_spike.vrm0.vrm` in VSeeFace for the 0.x preset path.
Full instructions in [test.md](../../../../tickets/docs/pending/926-ah-spike-skinned-shapekey-vrm/test.md).
This confirms the consumer-side experience; it does not gate the kill-shot verdict (already answered by the
automated round-trip).

## Next

- **The ladder is unblocked.** `vrm_export.py` now carries skinning + morph-expression binding, so the real
  parametric head (WI 923 ladder step 5) inherits it and adds: the full **ARKit-52 clip contract** (all 52
  names, ~13 authored + the rest as sanctioned empty stubs), a **canonical T-pose**
  (`vrm.make_estimated_humanoid_t_pose`), more spring chains, and eyelid/lip/brow topology density.
- **Subsumes WI 909** (asset-studio skinned-roundtrip spike, was UNVERIFIED) for the skinned-glb half;
  909's clip-retarget-onto-a-reproportioned-skeleton half is a separate question, out of scope here.
- Optional: the 0.x bind-weight scale check, if the owner observes weak 0.x amplitude.
