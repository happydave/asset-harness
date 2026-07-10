# Discover: rigged-avatars — AI mesh + auto-rig for game characters

**Status:** completed

## Subject

The `rigged-avatars` track: **rigged, animated characters** for AI-leaning generation — the
Sounding player/NPC avatar, and reusable across the other games. The last untouched track and,
per the track README, the **intentionally-weakest fit for AI generation**. As of 2026-07-08.

Two concrete design directions are in scope from the outset (see *Design directions* below):

1. **Rigid robotic humanoid** — a bipedal machine built as an **articulated rigid part-hierarchy**
   (no skinned deformation). Allowed to be a little janky / goofy.
2. **Stylized humanoid (Kerbal-tier)** — a low-poly, charming, forgiving-of-flaws character with a
   deliberate **failure-state transform** as a design hook (e.g. corn-cob person → popcorn).

## Motivation

Decide the track's approach for each direction, its **export contract** (glTF → Bevy, Y-up, metres),
and — load-bearing — **which tool chains produce commercially clean / redistributable outputs**.
Determine feasibility and recommend a first concrete prototype per direction. This scoping doc is
written *before* the external tool-landscape research; that research (a web-AI-researcher pass, prompt
below) populates the Findings and Assessment.

Sounding is vehicle-first and **crew is deferred** (First Playable is single-stage/uncrewed;
`sounding/project.md`), so this track is **not gating any game** right now — it is exploratory, and
that freedom is deliberate. The robotic direction also lines up with Sounding **WI 561 (articulated
multi-body / mechs)** and the rover physics core.

## Scope

- **In:** approach + tooling validation for the two directions; the glTF/Bevy **export contract**
  (rig = a bone hierarchy the engine can pose; humanoid rig retargetable to a mocap library);
  **licensing of every link** in each chain (mesh gen, auto-rig, auto-skin, animation/mocap);
  a first prototype recommendation per direction.
- **Out:** production character libraries; per-game art direction beyond validating a harness;
  facial rigs / lip-sync (later, if ever); realistic (non-stylized) humans — explicitly *not* a goal
  (uncanny valley, poor AI-only fit, poor cost/benefit for an academic sandbox).
- **Evidence gate:** every tool's output license is read from its actual license text / ToS, not
  assumed. The bar is the mechanical-kit standard — **fully clean, commercially redistributable**,
  no community-license or free-tier-redistribution baggage. Where a chain can't clear that bar, say
  so and prefer a chain that can.

## Design directions

### Direction A — Rigid robotic humanoid (janky/goofy OK)

The player *is* a small bipedal machine. Built as **solid parts on a bone hierarchy** — no skinned
mesh deformation — so it sidesteps the two things AI-only rigging is worst at (clean deformation
topology + weight painting) *and* the AI-mesh licensing problem, because it can largely **reuse the
mechanical-kit clean lane**: parametric Blender geometry (authored → fully ours) + `pbr-materials`
surfaces (Apache-2.0) + a hand-authored armature parenting parts to bones. "A humanoid built like a
rover." Jank is on-brand. Articulation ties to Sounding WI 561. *Hypothesis: this is the strongest
AI-only-viable, cleanest-licensed direction — research should confirm the rig/animation path.*

### Direction B — Stylized humanoid (Kerbal-tier) + failure-state transform

Low-poly, big-character, forgiving. The distinguishing hook is a **catastrophic-failure transform**
that fits the project's "failure is an acceptable outcome / the learning is the point" ethos.
Concepts on the table (owner-seeded + a few more to consider):

- **Corn-cob people** — kernelled humanoids; **failure → popcorn** (burst into fluffy white puffs).
  Best physical-comedy failure gag; the transform is a mesh/particle swap on a standard biped rig.
- **Badger people** — cute, likeable, sturdy anthropomorphic badgers (fur is a shading/rig cost;
  note it). No obvious failure-transform — would lean on ragdoll instead.
- *(seed, brainstorm later)* **Tuber / potato folk** — lumpy, expressive; failure → mash.
- *(seed)* **Mushroom folk** — cap-heads; failure → spore-burst.
- *(seed)* **Bean / legume people** — pill-shaped, near-capsule, cheapest possible rig.
- *(seed)* **Newt / salamander folk** — moist amphibian explorers; nods to Sounding's ocean half.

**Cross-cutting idea:** a "cooked/destroyed" **avatar state transform** (corn→popcorn, potato→mash,
mushroom→spores) is a reusable mechanic worth designing once — a swap from the rigged live mesh to a
burst VFX/ragdoll on a defined failure event. The `vfx` track already produces burst particle sets.

## Methodology & Sources

External web-AI-researcher pass (2026-07-08) surveying the current AI mesh-gen + auto-rig + animation
landscape, per-tool output licensing (read against actual license text / ToS), indie/solo-dev reports,
and Bevy import specifics. Full raw results:
[`research/web-research-rigged-avatars.md`](../../../tickets/docs/projects/asset-harness/research/web-research-rigged-avatars.md)
(under `tickets/docs/projects/asset-harness/research/`). Confidence labels below follow
`workflow/skills/evidence.md`. No local feasibility probe yet — that is the first prototype (see
Recommendation); the research is decisive enough to act on without it.

## Findings

### The gate is the MOTION DATA, not the mesh generator (Confirmed)

The dirtiest link in every AI *animation* chain is the motion corpus, not the mesh:

- **Text-to-motion is poisoned for commercial use (Confirmed).** Every usable open model (MDM,
  MoMask, MotionGPT, MotionDiffuse) is MIT *code* trained on **AMASS / HumanML3D**, whose license is
  **non-commercial research/education/artistic only** — and explicitly bars using the data to train
  methods for commercial use. The MIT badge on the repo does not launder the weights. **Cross
  text-to-motion off entirely.**
- **nvdiffrast is non-commercial and sits under the texture stages (Confirmed license; Hypothesis on
  reach).** NVIDIA Source Code License = non-commercial research/evaluation only. It underpins the
  **texture/PBR paint** stage of TRELLIS / TRELLIS.2 / Hunyuan3D. Reading (researcher opinion, not
  legal advice): the escape hatch is that the **shape/geometry** stages don't need nvdiffrast — only
  the paint stages do. **Generate geometry, texture in Blender.** Verify the import graph before
  relying on it.

### Licensing per tool (Confirmed unless noted) — the deciding axis

| Tool | Stage | Local? | Clears the "commercially clean + redistributable" bar? |
|------|-------|--------|--------------------------------------------------------|
| **Blender + Rigify** | geometry/rig/anim | ✅ | ✅✅ GPL tool, **outputs fully yours, unencumbered** |
| **UniRig** | auto-rig + skin | ✅ | ✅ **MIT — cleanest rigger**, template-free (handles odd proportions) |
| **Meshy (free)** | mesh | hosted | ✅ mesh under **CC BY 4.0** (commercial OK *with credit*) |
| **Meshy (Pro $20/mo)** | mesh | hosted | ✅ private ownership (don't publish to Community) |
| **Meshy anim / Mixamo / ActorCore** | anim | hosted | ⚠️ **ship-in-game OK, standalone redistribution NOT** |
| **AccuRIG 2.0** | rig | ✅ (Win) | ✅ likely (rig on *your* mesh; no facial bones on free; account required) |
| **Cascadeur Indie** | anim | ✅ | ✅ if <$100k/yr revenue; you own the animation ($8–19/mo) |
| **Hunyuan3D-2.1** | mesh | ✅ | ⚠️ Tencent community license; EU/UK/KR carve-out; LICENSE↔api_server conflict |
| **TRELLIS / TRELLIS.2** | mesh | ✅ | ⚠️ shape-only; ❌ texture stage (nvdiffrast NC) |
| **Tripo (free)** | mesh | hosted | ❌ legally-incoherent "CC BY 4.0 but non-commercial" — avoid |
| **Rodin / Hyper3D** | mesh | hosted | ⚠️ vague export/usage terms — must read ToS |
| **Anything World / RigNet / text-to-motion** | rig/anim | mixed | ❌ murky / NC / poisoned corpus |

**Clean chains that clear the bar:**
- Zero-cost + attribution: `Meshy free (CC BY 4.0) → UniRig (MIT, local) → Blender/Cascadeur Indie`.
- No vendor at all (cleanest): `Blender parametric geometry → own armature → procedural animation in
  Rust`. Researcher's recommended path for **both** directions.
- **Fails the bar for redistribution** (but fine to *ship inside a game*): anything touching Mixamo,
  Meshy, or ActorCore animation clips.

### Direction A — rigid robot: no AI in the loop (Confirmed feasible)

- **Rig:** Blender armature (standard humanoid bone layout) + **object-parent each rigid part to one
  bone** (`Ctrl+P → Bone`) → glTF exports a plain TRS-animated node hierarchy, **zero deformation by
  construction**, no weight painting. Variant: weight each vertex 1.0 to a single bone → a *skinned*
  humanoid that Mixamo/AccuRIG/mocap can retarget onto (the "mocap later" cheat code), at the cost of
  being back in skinned-mesh land.
- **Animation (researcher's ranked recommendation):** (1) **procedural/IK gait authored in Rust** —
  lowest-effort *for a programmer*, gives slope/speed/turn-in-place for free; `bevy_animation_graph`
  provides a two-bone IK graph node + state machines (Supported); (2) hand-key 4 poses @12fps —
  jank reads as *robot*, ~90 min; (3) **mocap retarget — don't** (human spine/shoulder micro-motion
  can't be expressed by rigid parts; more time stripping channels than keying).

### Direction B — stylized humanoid: Blender may beat AI (Supported)

- **Blunt finding:** a Kerbal-tier body is ~2k tris of capsules/boxes; authoring it in Blender is
  ~an hour and yields a clean, symmetric, named-part, parameterizable-for-NPC-variety mesh — likely
  **faster and cleaner than** generate → check-upright → remesh → fix-fused-limbs → auto-rig.
- **If pursuing the AI path:** **Meshy** is the only major generator with documented **T/A-pose
  control** + integrated remesh (edge loops at joints) — the riggable one. **UniRig** (MIT, local,
  template-free) is the better auto-rigger than Mixamo (whose hard gate is "distinguishable
  head/body/arms/legs" — where fused-limb AI meshes die). **AccuRIG** is a pragmatic free third
  option (19-joint rig, handles exaggerated proportions; no facial bones).
- **Where AI-only breaks (Confirmed, cross-source):** hands/fingers always, self-intersecting joint
  interiors, anything non-humanoid, thin protrusions. Cleanup budget: 20–60 min in Blender if the
  mesh is clean; throw away + regenerate if not. **No first-party report of an AI-character pipeline
  into Bevy specifically exists** — that's a real gap.

### Bevy import specifics (Confirmed / Supported)

- Current Bevy **0.19** (~June 2026) fixed skinned-mesh culling (arms-raised-vanish); automatic from
  glTF.
- **Rigid part-hierarchy is simpler than skinned:** no `SkinnedMesh`/inverse-bindposes, no
  `MAX_JOINTS` (256) cliff, no skinning pipeline footguns (e.g. a mesh carrying JOINT weights without
  a `SkinnedMesh` component panics in wgpu). The **animation system is identical** either way —
  `AnimationPlayer` + `AnimationGraph` on named `AnimationTarget`s.
- **The gotcha that bites everyone:** the glTF loader spawns the `AnimationPlayer` on a **descendant**,
  not on `SceneRoot`; `Query<&mut AnimationPlayer>::single_mut()` breaks on the second character —
  walk `iter_descendants` on `SceneInstanceReady`. Blender export: **apply scale first**; ship `.glb`,
  debug with separate `.gltf`+`.bin`. `Skein` glTF-extension flow can attach Bevy marker components
  per part (useful for a parts-based robot).

### Hardware reality for local mesh gen (Confirmed / Supported)

- **ROCm cards (gfx1151/gfx1201) are out** for local mesh gen — Hunyuan3D/TRELLIS depend on CUDA-only
  custom extensions (`custom_rasterizer`, `diffoctreerast`, `nvdiffrast`). Runs on the **RTX 5070 or
  nowhere**.
- **12 GB is tight:** Hunyuan3D-2.1 = 10 GB shape / 21 GB texture / 29 GB both → **shape fits, paint
  doesn't** (coincides with the "texture in Blender" advice). RTX 5070 is Blackwell (sm_120) →
  budget an evening rebuilding custom extensions against CUDA 12.8+/newer PyTorch (Hypothesis, from
  version pins).

## Assessment

- **Direction A (rigid robot): high feasibility, cleanest license, strongest fit.** No AI in the mesh
  path — reuses the mechanical-kit clean lane (authored geometry, Apache-2.0 PBR) + a hand-parented
  armature + a Rust procedural/IK gait. Zero licensing exposure, plays to the programmer strength,
  ties to Sounding WI 561. The scoping hypothesis holds.
- **Direction B (stylized humanoid): feasible, but AI may be a net loss vs. Blender.** The clean AI
  chain exists (Meshy free CC BY 4.0 → UniRig MIT → own/ship animation), but for a Kerbal-tier target
  the primitive-built Blender body is likely faster *and* cleaner. Worth **one honest AI attempt** to
  characterize the pipeline (that's the "for science" value), with a hard fallback to Blender.
- **Cross-cutting licensing rule for this track:** **never** ship *redistributable* animation data
  from Mixamo/Meshy/ActorCore/text-to-motion; own it (Cascadeur/Blender) or generate it procedurally.
  This is the mechanical-kit "clean lane" discipline applied to motion.
- **Owner decision (2026-07-08):** **attempt both directions "for science," robotic first / preferred.**

## Recommendation

Two prototypes, **A first**:

- **Prototype A — rigid robot walk:** parametric Blender biped (mechanical-kit lane) → armature with
  parts object-parented to bones → glTF → import into a Sounding/Bevy scene → **procedural two-bone-IK
  gait in Rust** (`bevy_animation_graph`). Deliverable: a janky-but-charming robot that walks, fully
  clean-licensed, no vendor. Findings via `_template/findings.md`.
- **Prototype B — stylized humanoid, one AI attempt then fallback:** `Meshy free (CC BY 4.0) → UniRig
  (MIT, local) → own animation`; if the first ~3 meshes come back with fused limbs, **stop and build
  the Kerbal-tier body in Blender** from primitives. Parameterize for NPC variety. Design the
  **failure-state transform** (corn→popcorn as a live-mesh → burst-VFX/ragdoll swap) as a reusable
  avatar mechanic; the `vfx` track already produces burst particle sets.

Both prototypes become tracked work items when picked up. Record the Bevy `AnimationPlayer`-on-
descendant pattern and the Blender **apply-scale-before-export** rule in whichever lands first.

## Open Questions (residual)

- Does the shape-only stage of TRELLIS/Hunyuan truly avoid nvdiffrast? (Verify the import graph before
  any local-mesh-gen prototype — only relevant if Meshy-free is rejected.)
- Tripo-free and Rodin terms are ambiguous → get written support confirmation before relying on
  either (both currently rejected in favour of Meshy-free, so non-blocking).
- Exact `bevy_animation_graph` / `bevy_mod_inverse_kinematics` version compatibility with the Sounding
  Bevy version — confirm at Prototype A planning.
