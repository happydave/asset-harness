# Findings: stylized expressive head (fuller ARKit morph set)

**Date:** 2026-07-15
**Track:** rigged-avatars
**Verdict:** works

## Goal

A readable, Kerbal-tier **stylized parametric head** carrying a **fuller ARKit morph set** — the first real
cut of the stylized head archetype (WI 923 VTuber ladder step 5), and a proper expressive demo for the WI
934/935 Studio VRM inspector (corn has no morphs; the WI 926 `face_spike` is a featureless probe). Skinned,
with the full **ARKit-52 declared** as expression clips (authored ones bound, the rest empty Perfect-Sync
stubs). asset-harness WI 936.

## Tooling

- **Blender 4.2.22 LTS** + **saturday06 VRM add-on v4.4.0** on ai2 (`~/blender-4.2/blender`, WI 933).
- **New** `rigged-avatars/prototypes/blender_expressive_head.py` — skinned head+body on the 19-bone rig
  (reuses `blender_corn.py` rig helpers), eyes/brows/mouth as **material-distinct regions on the single
  deformable head mesh**, 14 authored ARKit morphs, `--previews` readability renders.
- Exports via the shared **`vrm_export.py`** (`_set_expressions`, unchanged — it already emits empty custom
  expressions for stub bind-lists).

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Blender + VRM add-on | GPL-3.0-or-later + MIT | tool only | — | imposes nothing on output |
| head geometry / rig / morphs | authored (ours) | yes | yes | Blender primitives + hand-authored morphs |

- **Effective output license:** **clean**. VRM 1.0 permissive meta (corporation/everyone/allowRedistribution);
  VRM 0.x CC0. ARKit *names* are Apple's public API vocabulary — naming our own morphs after them is clean
  (WI 923 finding); describe as "ARKit-compatible", not "ARKit®".

## Hardware

- ai2 — CPU. Seconds.

## Inputs

- `blender_expressive_head.py --out ~/wi936 --previews`. Deterministic (parametric, fixed displacements).

## Result

- **Samples:** [`samples-2026-07-15-expressive-head/`](samples-2026-07-15-expressive-head/) —
  `expressive_head.vrm` (1.0), `.vrm0.vrm` (0.x), `.glb`, manifest, and 6 preview PNGs
  (`preview_{neutral,blink,smile,jawOpen,angry,surprised}.png`).
- **What worked (14/14 automated + readability by eye):**
  - **14 authored ARKit morphs**, exact names: eye blink/wide/squint L/R, browInnerUp, browDown L/R, jawOpen,
    mouthSmile/Frown L/R — each a distinct region deformation.
  - **Full ARKit-52 declared** as VRM 1.0 customs: the 14 authored bound, **38 empty Perfect-Sync stubs** —
    the file is Perfect-Sync-shaped from day one (VSeeFace-legal empty clips). The WI 935 inspector filter
    shows only the 14 bound ones — the intended UX.
  - **Presets composed** from authored morphs (blink/happy/angry/sad/aa/surprised/relaxed); VRM 0.x preset
    equivalents.
  - **Skinned** (armature modifier + auto weights); both VRMs re-import; game-lane `.glb` kept.
  - **Readable:** dark eyes + brown brows + red mouth on the single deformable mesh; neutral/blink/smile/
    jawOpen/angry/surprised each visibly distinct (see previews). Stylized/blocky, but a clear expressive
    face — the point of the WI.
- **Deferred:** eye bones/gaze (the `eyeLook*` shapes are stubs anyway); a cleaner blink needs real eyelid
  loop topology (future real-rig work).

## Repeatability

- Deterministic. `--previews` reproduces the readability renders (front-facing TRACK_TO camera).
- **Gotcha recorded:** headless preview renders need (a) the camera on the **+Y (front)** side — the face is
  at +Y, so a −Y camera photographs the featureless back — and (b) `view_layer.update()` before each render,
  or shape-key state isn't evaluated and all frames come out identical. The exported asset is unaffected by
  either (morphs verified via depsgraph-evaluated displacement).

## [visual/manual] — owner gate

Load `expressive_head.vrm` in the Studio VRM inspector (drag onto the workshop viewport). The 14 bound
expressions should appear (stubs hidden by the WI 935 filter) and each read as a clear facial deformation;
the presets drive too. This is the dedicated expressive demo asset.

## Next

- The **stylized head archetype's first cut** — feeds the inspector and advances WI 923 step 5. The real
  step-5 head would add: eyelid/lip loop topology for cleaner morphs, eye bones + gaze, texture, and the
  authored-morph tranches beyond the core 14.
- `vrm_export.py` remains the shared exporter; the 52-name expression contract is now exercised through it.
