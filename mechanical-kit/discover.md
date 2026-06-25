# Discover: mechanical-kit — parametric hard-surface parts + AI surface

**Status:** completed

## Subject

The `mechanical-kit` track: modular, snap-together **mechanical part meshes** — the discrete,
hard-surface components a build system mounts onto a chassis (wheels, struts, seats, antennae, solar
panels, bumpers; later rocket tanks/stages/fins). As of 2026-06-24. The one substantial track never
started.

## Motivation

Decide the track's approach and, critically, its **export contract** — who consumes these parts and
in what shape. Determine feasibility and licensing, then recommend a first concrete deliverable.

## Scope

- **In:** approach validation; the **consumer contract** (Sounding's part system); tooling
  (Blender headless on `ai2` + pbr-materials for surface); licensing; the first part catalog.
- **Out:** DWA (it is 2D — its modules are served by the `2d` track, not this one); the voxel
  **chassis** mesh (that is the Sounding *voxel-skinning* core + `pbr-materials`, not this track); a
  full production part library; per-game art direction.
- **Evidence gate:** the contract is read from Sounding's code/design, not assumed.

## Methodology & Sources

Read Sounding's `crates/sim/src/voxel.rs` (`Part` / `PartKind`, WI 607/630), `design-voxel-skinning.md`,
`design-workshop.md`, and the `3d-static-props` discovery (image-to-3D suitability). Ran a Blender
headless feasibility probe on `ai2` (parametric part → glTF).

## Summary

mechanical-kit is **well-posed, high-value, and fully clean-licensed**, and it has a **named, waiting
consumer**: Sounding's voxel-skinning design explicitly *defers "authored per-part meshes" to the
`3d-static-props` / `mechanical-kit` tracks*, and `voxel.rs` says the catalog parts' "meshes land in
**WI 608**." So this track's first job is concrete: produce the **WI 608 part-mesh catalog**. The
approach in the track README is correct — **parametric Blender geometry for the shape** (image-to-3D
is *worst* at mechanical revolved solids with mount points) **+ AI for the surface** (pbr-materials).
Feasibility confirmed: Blender headless on `ai2` builds a parametric part and exports glTF.

## Findings

### Consumer is Sounding; the contract is the `Part` system (Confirmed)

- DWA is 2D (modules already served by the `2d` track), so mechanical-kit is effectively
  **Sounding-only** for now. Sounding renders the **voxel chassis** via its own skinning core +
  `pbr-materials`; mechanical-kit supplies the **discrete catalog parts** that mount onto it.
- `Part { mount: DVec3, mass, kind, station }` — `mount` is a position **in metres, in the craft
  lattice frame** (same frame as cell centres). So the **mesh origin = the mount point**, units
  **metres**, glTF **Y-up** (Bevy). Parts are sized relative to the build's `cell_size`
  (`WheelPart::for_cell_size`), so the generator should be **cell_size-parameterised**.
- **Catalog (PartKind):** `Suspension` (strut), `Rim` (hub), `Tire` (split from the legacy
  monolithic `Wheel` in WI 630 — a wheel station = Suspension+Rim+Tire), `Seat`, `Antenna`,
  `SolarPanel`, `Bumper`. A wheel is therefore **three component meshes** assembled visually, not one.
- **Rocket-domain parts** (fuel tank, engine bell, nose cone, fins, decoupler/stage ring) are the
  natural next catalog once the rover parts land — same parametric approach.

### Approach: parametric shape + AI surface (Confirmed feasible)

- Parts are mostly **revolved/extruded primitives** (cylinders, cones, rings, boxes) with bevels —
  exactly what whole-mesh AI generation handles *worst* (the `3d-static-props` finding: Hunyuan/MoGe
  give organic blobs, and carry license baggage). So **geometry is authored parametrically in
  Blender** (bpy primitives + modifiers; geometry-nodes optional later) — achievable without modeling
  skill — and **AI supplies the surface**: `pbr-materials` (Z-Image albedo → normal/roughness/AO) plus
  optional AI **decals/greebles** as textures.
- **Feasibility probe (Confirmed):** on `ai2`, `blender --background --python` built a capped,
  beveled cylinder, set origin to the base (mount convention), and exported a 25 KB `.glb`. (Draco
  compression unavailable — irrelevant; uncompressed glTF is what Bevy wants.)

### Tooling

- **Blender 4.0.2 headless on `ai2`** over SSH (already used for terrain decimate/displace/optimize)
  — the same pattern: a Python generator script driven remotely, glb pulled back. glTF exporter works.
- **pbr-materials** track for surfaces (already Bevy-validated via the `-- materials` scene).
- No ComfyUI dependency for the *geometry*; ComfyUI only for the AI material/decal textures.

### Licensing — the cleanest 3D path (Confirmed)

| Artifact | License | Commercial / redistribute |
|----------|---------|---------------------------|
| Blender (tool) | GPL | outputs are **yours**; GPL does not touch generated assets |
| Our parametric geometry | authored | fully ours |
| Z-Image PBR surfaces | Apache 2.0 | clean |

- **Effective:** fully clean / commercially redistributable — **no** Hunyuan-style community-license
  baggage (the wall the `3d-static-props` hero-prop path hit). Mechanical-kit is the **clean 3D lane**.

## Assessment

- **Feasibility: high.** Mechanism proven; consumer contract known and small; reuses the Blender-on-
  `ai2` and pbr-materials machinery.
- **Value: high.** Fills the last untouched substantive track and **unblocks Sounding WI 608**
  (catalog part meshes), which the build/workshop work is waiting on.
- **Risks:** (1) **orientation/scale contract** must match Sounding's `Part.mount` + rover-assembly
  axes exactly — confirm per part at import (esp. wheel axle axis). (2) Parametric parts can look
  **samey** — mitigate with AI decals/greebles + material variety, not more geometry. (3) The wheel
  is **three meshes** (Suspension/Rim/Tire) that must align when assembled — design their origins
  together.

## Recommendation

**Stand up the track with the WI 608 part-mesh catalog as the first prototype.** A parametric Blender
generator (`prototypes/generate_parts.py`, run on `ai2`) producing the rover catalog —
**Tire, Rim, Suspension, Seat, Antenna, SolarPanel, Bumper** — as `.glb` with **origin at the mount
point, metres, Y-up, cell_size-parameterised**, skinned with a `pbr-materials` metal/rubber/panel
set; then **import one into a Sounding scene** (a wheel station, or the solar panel) to prove the
seam against `Part.mount`. Rocket parts (tank/bell/nose/fins/decoupler) follow as a second catalog.

## Open Questions

- Exact part **orientation** convention from rover assembly (wheel axle axis; "forward"/"up" of seat,
  antenna, solar) — read from `crates/sim/src/rover.rs` / the editor at prototype time.
- How **decals/greebles** are applied — baked into the material texture vs. separate decal meshes.
- Whether **geometry nodes** earn their complexity over plain bpy primitives for v1 (likely not).
- `cell_size` range to target so parts look right across build scales.
