# Findings: Kerbal-tier corn-person + corn→popcorn (Direction B, Prototype B)

**Date:** 2026-07-09
**Track:** rigged-avatars
**Verdict:** works

## Goal

Prove **Direction B** (a Kerbal-tier stylized humanoid) via the Blender-primitives path, and — the
distinctive part — the **failure-state transform** the discovery flagged as a reusable avatar
mechanic. Concrete concept: a **corn-cob person** that **pops into popcorn** on catastrophic failure.
Engine-agnostic glTF for all three games; Sounding first.

## Tooling

- **Base model:** none — **no AI** (the discovery's "hard fallback to a primitive-built Blender body,"
  which for Kerbal-tier is likely the *primary* path).
- **Workflow / scripts:** [`prototypes/blender_corn.py`](../prototypes/blender_corn.py) (builds both
  the rigged corn-person and the popcorn-burst), plus the reused/generalized
  [`bake_glb_extras.py`](../prototypes/bake_glb_extras.py) (now `--name`, and `--merge <clip>` to
  collapse a per-object export into one named clip) and [`render_clip.py`](../prototypes/render_clip.py)
  (generic: auto-frames the bbox **swept over all rendered frames**, selects a clip by name).
- **Other software:** Blender 4.0.2 headless on `ai2`.

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Blender (tool) | GPL | yes | yes | outputs are yours |
| Authored geometry (corn + puffs) | ours | yes | yes | this repo |
| Hand-keyed motion (idle/walk/pop) | ours | yes | yes | authored — not from any mocap/AI corpus |

- **Effective output license:** fully clean / commercially redistributable. No attribution obligation.

## Hardware

`ai2` (gfx1201 R9700), Blender 4.0.2, EEVEE preview. No CUDA/mesh-gen involved (Direction B's Blender
path, like Direction A, runs anywhere Blender does).

## Inputs

Fully parametric/deterministic; the popcorn scatter is seeded (`random.seed(1234)`), so the burst is
identical every run. Kerbal proportions (~1.3 m, big head); corn-person reuses the **Prototype A
armature layout + walk keys verbatim** (amplitudes trimmed for stubby legs).

## Steps

1. `scp prototypes/{blender_corn,render_clip,bake_glb_extras}.py ai2:/tmp/`
2. `ssh ai2 '... blender_corn.py -- --out /tmp/corn_out'`  (builds corn.glb + popcorn_burst.glb)
3. `scp` the glbs / debug / manifests back to `prototypes/out/`
4. `python3 bake_glb_extras.py --dir out --name corn`
5. `python3 bake_glb_extras.py --dir out --name popcorn_burst --merge pop`
6. `ssh ai2 '... render_clip.py -- --glb .../corn.glb --clip walk --prefix corn_walk'` and
   `... --glb .../popcorn_burst.glb --clip pop --prefix pop --frames 1,3,5,7,9,11,13,14`

## Result

- **Samples:** `prototypes/out/{corn,popcorn_burst}.glb` (+ `debug/` + `*_manifest.json`), and the
  preview sheets `corn_walk_00..07.png`, `pop_00..07.png`.
- **`corn.glb` (verified):** 41 nodes, 21 meshes, 1 skin (skeleton only), **0 skinned meshes** (rigid
  bind holds), clips **`idle` + `walk`** with baked extras (walk carries the foot-event schedule), and
  a **`failure_transform`** link (`corn` → `popcorn_burst.glb`) in the root `extras`.
- **`popcorn_burst.glb` (verified):** a seeded scatter of 22 popcorn puffs, exported per-object then
  **merged at the glTF level into a single `pop` clip** (loop:false / oneShot) — `66` channels
  (22 puffs × translation/rotation/scale).
- **Round-trip:** both baked glbs re-import + animate in Blender's glTF loader; GLB structure valid.
- **Visual:** the corn-person reads as a charming, goofy Kerbal-tier corn creature (kernelled cob
  body, green husk limbs, **mini-corn-cob head** with a husk tuft — see the head bake-off below); the
  `pop` reads clearly — tiny cluster → mid-air burst of white puffs → settled pile.
- **What worked / notable:**
  - **The Prototype A rig generalized verbatim** — same armature + walk keys drive a completely
    different mesh. That is the reusable core: a stylized humanoid is "new geometry on the proven rig."
  - **Failure transform = a swap of two clean assets** linked by metadata, exactly as the discovery
    framed it. Cheap: the burst is a seeded, object-animated one-shot, no rig.
  - `--merge` in the baker cleanly collapses Blender's per-object SCENE export into one named clip.
- **What's rough (acceptable for a prototype):** puffs are low-poly (fine, stylized).

### Head bake-off (2026-07-09)

The head is a parameterized variant (`blender_corn.py -- --heads classic,human,kernel,cob`; portraits
via `render_clip.py --portrait`; comparison in `prototypes/out/head_compare.png`):

- **classic** — cream dome (original); reads as a pale helmet on a corn body, least "corn."
- **human** — taller oval + nose + hair; most person-like, but incongruous on a corn body.
- **kernel** — one big corn-kernel head (tooth silhouette), yellow; iconic, unifies by colour.
- **cob** — a mini corn cob (kernel bumps + green husk tuft), yellow. **Owner-selected default.**

The two yellow heads (kernel/cob) unify the character far better than the pale ones (which read as "a
humanoid wearing a corn suit"). `corn.glb` now ships the **cob** head (`head_variant: cob` in the
manifest); the other three regenerate on demand via `--heads`.
- **Knee direction (fixed 2026-07-09).** Initially a reverse/bird knee (felt especially wrong on a
  humanoid); fixed by negating the `shin` `rot_x` so the calf tucks backward. See the rigging lesson
  in the [robot findings](2026-07-09-rigid-robot-walk.md).

## The failure-transform mechanic (reusable)

Two separate assets — the **live rigged avatar** and a **burst asset** — linked by a
`failure_transform` in the avatar's metadata. On a catastrophic-failure event the engine **despawns
the avatar and spawns the burst at its transform**, plays the one-shot `pop`, and leaves the settled
pile (or fades it). This generalizes cleanly to the other Kerbal-tier concepts: **badger → tumbling
ragdoll**, **tuber → mash**, **mushroom → spore-burst**, **bean → split-pod**. The corn→popcorn case
is the showcase because the burst is *literally* a different food.

## AI-path recipe (owner-run "for science" comparison)

The discovery's other Direction-B half is a single **AI-mesh attempt**; it can't run in-session
(Meshy is a hosted account; UniRig is a heavy local CUDA/model setup). To run it yourself:

1. **Mesh — Meshy (free tier).** Generate a stylized humanoid; **set Pose to T-pose or A-pose** in
   generation (gives the rigger a clean stance), then use **Remesh** for quad topology + joint edge
   loops. Prompt seed: *"a stylized chibi corn-cob person, T-pose, big rounded head, stubby limbs,
   low-poly game character, clean symmetric silhouette, arms and legs clearly separated from body."*
   **License:** free output is **CC BY 4.0** — commercial OK **with attribution** ("Model created with
   Meshy – CC BY 4.0"). If limbs fuse to the torso on the first ~3 tries, **stop** — the Blender
   corn-person here is faster and cleaner.
2. **Rig — UniRig (local, MIT).** Predicts skeleton + skinning weights; template-free (tolerates odd
   proportions better than Mixamo, whose gate is "distinguishable head/body/arms/legs"). Runs on the
   RTX 5070 (CUDA). No account, no ToS on the output.
3. **Animation — own it.** Cascadeur Indie (<$100k/yr) or hand-key in Blender; **or ship** Mixamo/Meshy
   library clips *inside the game only* (do **not** redistribute the raw animation files, and **never**
   use text-to-motion output — AMASS/HumanML3D-trained weights are non-commercial). See
   [discover.md](../discover.md) for the full licensing table.
4. **Compare** the AI mesh (after cleanup time) against `corn.glb` on: minutes to a rigged, animated,
   in-engine character; topology cleanliness; and license friction. The discovery's hypothesis is that
   Blender wins for Kerbal-tier — this is the experiment that confirms or refutes it.

## Repeatability

Deterministic (seeded scatter; no AI/sampling). Re-runnable headless on `ai2`.

## Next

- Other Kerbal-tier concepts on the same rig (badger, tuber→mash, mushroom→spores, bean, newt) — each
  is new geometry + a burst asset; the pipeline is now proven.
- Downstream (game repo): wire the failure swap (despawn avatar → spawn `popcorn_burst` on the event);
  read `failure_transform` from the sidecar/extras.
- Optional polish: corn head tint / silk tuft; denser puffs; a squash-and-stretch on the pop.
