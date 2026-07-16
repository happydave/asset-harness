# Findings: MPFB2 as a CC0 skinned-body donor (timeboxed evaluation)

**Date:** 2026-07-15
**Track:** rigged-avatars
**Verdict:** partial — **qualified yes as a reserve donor; no for the current Kerbal-tier stylized direction**

## Goal

Decide whether to build the VTuber avatar's **body** on **MPFB2** (the MakeHuman community's Blender
add-on, WI 923's cleanest-licence donor) instead of authoring all geometry parametrically from primitives
(the WI 882/885 path). **Body only** — WI 923 settled that MPFB2 has *no ARKit shape keys* (its facial
system is bone-based), so the ~26–32 face morphs are ours to author regardless (WI 936 already does this).
The narrow question: **does a CC0 skinned body with correct topology + weights save more work than
reshaping its realistic topology to the stylized target costs?** asset-harness WI 927.

## Tooling

- **Blender 4.2.22 LTS** on ai2 (`~/blender-4.2/blender`, WI 933) — the same install that carries the VRM
  add-on, so MPFB2 composes with the VRM export pipeline in-process.
- **MPFB2 v2.0.17 (built from source, tag near v2.0.16)** — installed headlessly as a **Blender 4.2
  extension** (`bl_ext.user_default.mpfb`). Recent MPFB2 releases ship no zip asset; the add-on is built by
  zipping `src/mpfb/` (manifest at zip root) and installing via
  `blender --command extension install-file -r user_default -e mpfb.zip`.
- **New** `rigged-avatars/prototypes/mpfb2_body_eval.py` — headless evidence harness: `create_human()` +
  `add_builtin_rig()`, dumps topology/rig/bbox JSON, saves `.blend` + `.glb`, renders a front preview.
  Uses only the **bundled CC0 base mesh + built-in rigs** — no `makehuman_system_assets` pack needed for a
  body assessment (skins/clothes/eyes would need it).

## Licensing (commercial / redistribution) — verified from primary text

Read from the installed repo's `LICENSE.md` + `LICENSE.ASSETS.md` (not just a summary):

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| MPFB2 source code | **GPL-3.0-or-later** | tool only | — | `LICENSE.md` §B; manifest `SPDX:GPL-3.0-or-later` |
| MPFB2 bundled assets (base mesh, **targets, rigs, poses, expressions**, JSON) | **CC0 1.0** | **yes** | **yes** | `LICENSE.md` §C + `LICENSE.ASSETS.md` |
| Output from MPFB (scripted or GUI) | your data — no claim | yes | yes | `LICENSE.md` §D (verbatim) |

- **§D verbatim:** *"no output from MPFB contains any trace of program logic … regardless of whether you use
  the UI as such or if you call functions of MPFB via a script … there is no limitation on what you can do
  with this combined output."* Scripted export is explicitly enumerated as clean output.
- **Effective output license:** **clean** — a body derived from MPFB2's CC0 assets ships in a closed-source
  commercial game with no obligation. The GPLv3 covers the *add-on code*, which we do not redistribute.
- **The trap, confirmed and recorded:** **MakeHuman standalone's CC0 grant carves out automated/mass
  exports** (AGPL applies when linking as a library, running in server mode, or scripting bulk exports —
  landing *exactly* on our architecture). **MPFB2 is the version WITHOUT that carve-out** (GPLv3-not-AGPL,
  the Blender-aligned relicense). Textbook repo rule: *read the licence of the assets, not just the code* —
  and know which sibling you are using.

## Hardware

- ai2 — CPU only. Generation + export + render: seconds per rig.

## Evidence (measured, not asserted)

Two built-in rigs generated on the identical bundled base mesh
([`mpfb_body_*.json`](samples-2026-07-15-mpfb2-body/)):

| | base mesh (with helpers) | **clean body** (helpers baked off) |
|---|---|---|
| vertices | 19,158 | **13,380** |
| polygons | 18,486 | 13,378 |
| tris / **quads** / ngons | 0 / 18,486 / 0 | 0 / **13,378** / 0 (**100% quads**) |
| height | 1.659 m (realistic) | — |

- **Topology: production-grade.** Pure-quad, proper edge loops around joints/face — the kind of clean
  deformation topology that is genuinely hard and slow to author by hand. (The ~19k "with helpers" count
  includes MakeHuman's clothes-fitting *helper shell*; `ExportService.bake_modifiers_remove_helpers()`
  strips it to the ~13.4k game body — the standard export prep.)
- **Rig: two useful options, both skinned with imported weights.**
  - `game_engine` — **53 bones**, standard UE/game naming (`pelvis`, `spine_01/02/03`, `clavicle/upperarm/
    lowerarm/hand_[lr]` + full fingers, `thigh/calf/foot/ball_[lr]`, `neck_01`, `head`). **Maps 1:1 onto our
    19-bone VRM humanoid contract** (pelvis→hips, spine_01→spine, spine_02/03→chest, …) with fingers + toe
    balls as free extras. This is the donor rig.
  - `default` — 163 bones, full facial + finger + toe rig; overkill for a body, but confirms MPFB carries a
    complete facial **bone** rig (consistent with WI 923: face is bone-based, no ARKit morphs).
  - (My JSON's `vrm_slot_coverage` under-counts — the token matcher expected `thigh.l`/`upperarm.l` dots but
    the rigs use `thigh_l`/`upperarm01.L`; inspecting the bone lists, **all 19 slots are present** on both.)
- **Aesthetic: unambiguously realistic adult human** — see [`mpfb_body_clean.png`](samples-2026-07-15-mpfb2-body/mpfb_body_clean.png):
  realistic proportions, anatomy, and (on the `default` rig) a realistic face. Our stated target is
  **stylized anime**.

## Decision — with reasoning ("no" was an acceptable outcome; this is a *qualified* answer)

Every hard gate passes: **the scripted headless path works**, the **CC0 licence is clean and verified**, the
**topology is production-grade**, and the **`game_engine` rig maps onto our VRM humanoid**. The only mismatch
is aesthetic — realistic vs stylized — and it splits cleanly:

- The **face** is where realistic-vs-stylized diverges hardest (dense realistic mouth/eye loops fight a big-
  eyed anime face). **The face is out of scope here** — ours to author regardless (WI 936).
- The **body** differs from a stylized body mostly in **proportions** (limb thickness, height-to-head ratio),
  not topology — and **MPFB's macro/modeling-target system reshapes proportions natively without damaging the
  quad flow**. So a *semi-realistic / anime-with-human-proportions* body is a strong fit for MPFB2.

But the track's current stylized direction is **Kerbal-tier blocky** (WI 936's head archetype). For that look:

- A **primitive-authored body** (WI 882/885) is *simpler, cheaper, already clean, and a better aesthetic
  match* — blocky forms are trivial primitives, and MPFB's realistic 13.4k-vert mesh would **fight** the
  blocky style rather than help.
- Reshaping a realistic human down to Kerbal-blocky is *more* work than building blocks, not less.

**Decision:**
1. **Do NOT adopt MPFB2 for the current Kerbal-tier stylized avatar.** The proven parametric-primitive path
   wins on cost *and* aesthetic fit. **No sunk cost** — the eval cost ~half a day and leaves a reusable,
   installed, licence-cleared capability.
2. **Keep MPFB2 as a validated reserve body donor** for any future *semi-realistic / realistic* avatar
   (e.g. the deferred WI 930 realistic archetype), where its clean CC0 topology + weights + VRM-mappable rig
   would be a large, legitimate shortcut over hand-authoring a skinned human body. The install + harness are
   in place; re-picking it up is cheap.

## Repeatability

Fully scripted + deterministic: `mpfb2_body_eval.py --rig <default|game_engine> --out <dir>` on ai2 after the
one-time extension install. Same base mesh every run; artifacts committed as the sample set.

## Next

- If **WI 930 (realistic head archetype)** or any realistic-avatar direction lands, revisit MPFB2 as the body
  donor and evaluate its **macro/modeling-target reshaping** + the **`game_engine` → VRM humanoid bone remap**
  end to end through `vrm_export.py`.
- The Kerbal-tier body stays on the primitive path; nothing to fold into the harness now.
