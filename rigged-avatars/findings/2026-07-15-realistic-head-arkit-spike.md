# Findings: ARKit morphs on the MPFB2 CC0 realistic head (spike)

**Date:** 2026-07-15
**Track:** rigged-avatars
**Verdict:** works — the unblocked slice of WI 930 (realistic head archetype) is de-risked

## Goal

Prove the one piece of WI 930 (realistic head archetype) that is **unblocked** — that the **MPFB2 realistic
head topology can carry ARKit-named shape keys** that deform *convincingly*, and that they export through the
existing `vrm_export.py` **unchanged**. This is the payoff the WI 936 smooth-sphere stylized head could not
deliver (its blink read messy for lack of eyelid loops). It does **not** resolve 930's gated parts (FLAME /
dense-topology substrate choice, near-full 52-shape authoring, head isolation, realistic texture lane); those
stay with 930. asset-harness WI 938 (spike toward 930). Owner chose this path 2026-07-15.

## Tooling

- **Blender 4.2.22 LTS** + **MPFB2 v2.0.17** (extension `bl_ext.user_default.mpfb`) + **saturday06 VRM
  add-on v4.4.0** on ai2 — all three in one headless process.
- **New** `rigged-avatars/prototypes/blender_realistic_head_spike.py`: generates the MPFB `default`-rig human
  (163-bone facial rig), bakes off the helper shell (WI 927) → clean **13,380-vert pure-quad** head+body,
  authors 5 ARKit morphs, exports **VRM 1.0 + 0.x + glb** via the shared `vrm_export.py` (**unchanged**).

## The authoring result — a two-technique recipe (the spike's main finding)

Authoring ARKit morphs on the realistic head split cleanly into two techniques, and **which one you need
depends on whether the shape is skinned articulation or a localized surface deformation**:

| Technique | Used for | How | Why |
|-----------|----------|-----|-----|
| **Bone-pose bake** | `jawOpen` | Rotate the `jaw` bone; store the **posed-minus-rest evaluated delta** as the shape key | The mouth-opening is **skinned to the lip (`oris`) bones, not the `jaw` group** — so a jaw-group displacement drops the chin but the lips stay shut. Posing the bone lets MPFB's skinning carry the lips **open** correctly (46 mm, reads as a proper open mouth). |
| **Weight-mask displacement** | `eyeBlinkLeft/Right`, `mouthSmileLeft/Right` | Displace verts of a facial bone's **weight group** along a world direction, weight = smooth falloff | Localized surface shapes have a single dominant muscle group (`orbicularis03.L/R` eyelid, `risorius03.L/R` mouth corner); the group is the mask, we pick the direction. Clean, no bone-frame math. |

**Dense realistic topology paid off exactly where WI 936 predicted:** the `eyeBlink` closes the eyelid to a
clean slit over the real eye socket (see `rhead_eyeBlinkLeft.png`) — the crisp single-eye closure the WI 936
smooth sphere could not produce. This empirically confirms 936's reflection ("the real step-5 head needs
eyelid/lip/brow loop topology").

Amplitudes here are **deliberately exaggerated for legibility** (a demo); real WI 930 would calibrate to ARKit
reference blendshape amplitudes.

## Licensing (commercial / redistribution)

Inherited from WI 927, verified there from primary text — unchanged here.

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| MPFB2 base mesh + rig (donor) | **CC0 1.0** | yes | yes | `LICENSE.md` §C + `LICENSE.ASSETS.md` (WI 927) |
| authored morphs (bone-bake + weight-mask) | ours | yes | yes | scripted, our creative input |
| Blender + MPFB2 + VRM add-on | GPL-3.0 / GPL/MIT | tool only | — | §D: no claim on scripted output |

- **Effective output license:** **clean.** VRM 1.0 permissive meta; VRM 0.x CC0.

## Hardware

- ai2 — CPU. Generation + 5 morphs + 6 renders + dual VRM export: ~1 min.

## Result

- **Samples:** [`samples-2026-07-15-realistic-head-arkit-spike/`](samples-2026-07-15-realistic-head-arkit-spike/)
  — `realistic_head.vrm` (VRM 1.0 demo fixture) + 6 head renders (neutral + 5 morphs) + `realistic_head_evidence.json`.
- **Automated (all pass):**
  - Generation: clean 13,380 v / 13,378 poly; 5 authored shape keys with **exact ARKit names**.
  - Morph displacement: jawOpen 62 mm (bone-bake), eyeBlink 15 mm, mouthSmile 16 mm (weight-mask).
  - **glb re-import:** all 5 ARKit shape keys survive + armature intact.
  - **VRM 1.0 re-import:** all 5 as **custom expressions**; **15/15 required humanoid slots bound**; `blink`
    preset = 2 binds, `happy` preset = 2 binds.
- **Readability (my renders):** neutral reads as a genuine realistic face; jawOpen = proper open mouth;
  eyeBlink = clean single-eye closure; mouthSmile = visible corner lift. Distinct and plausible.
- **Note:** the MPFB base mesh ships its own macro-detail shape keys (`$md-…`, age/gender/ethnicity); they
  ride along in the export at value 0 (harmless). A clean WI 930 asset would prune or freeze them.

### Bug found + fixed by owner review (2026-07-15): jawOpen was morphing the whole body

The owner's inspector review flagged that expressions moved the whole body. A region check confirmed a real
bug: the first `jawOpen` (baked via `modifier_apply_as_shapekey`) moved **all 9,140 body verts** (avg 40 mm)
— because that operator stores the *fully-evaluated* mesh **absolutely**, silently including the active
macro-detail shape keys (`$md-…` proportions). The jawOpen delta thus carried the whole-body proportioning and
double-applied it at weight 1. **Fix:** bake the shape from the **posed-minus-rest evaluated delta** (macros
active in both → they cancel), leaving only the jaw articulation. After the fix the region check shows body
verts moved drop to **80 verts, max 7 mm** (the throat skin under the jaw, which legitimately follows an open
mouth) — and the mouth still opens cleanly. **General lesson for WI 930:** never bake a corrective/expression
shape from `modifier_apply_as_shapekey` on a mesh carrying active shape keys; use a posed-minus-rest delta.
(The weight-mask morphs were never affected — they displace relative to Basis and stay local.)

## Repeatability

`blender_realistic_head_spike.py --out <dir>` on ai2 (MPFB2 + VRM add-on installed). Deterministic; the jaw
rotation sign is auto-detected (the sign that lowers the chin), so no per-run tuning.

## Next (feeds WI 930)

- **The pipeline + topology are proven; 930's remaining work is unchanged:** choose the dense-topology
  substrate (this MPFB head vs FLAME 2023 Open — still human-gated), author the **near-full 52-shape** set
  (the two-technique recipe above is the method; calibrate amplitudes to ARKit references), **isolate the
  head** (neck seam) if a head-only archetype is wanted, and pick the **realistic texture lane** (Scenario /
  self-trained LoRA). Eye-gaze bones (MPFB has `eye.L/R`) make the 8 `eyeLook*` shapes cheap.
- The `default` rig → VRM humanoid map (`HUMANOID_MPFB_DEFAULT` in the generator) is reusable for the MPFB
  body from WI 927.
