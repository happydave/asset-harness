# Findings: rover part-mesh catalog v1 (parametric Blender)

**Date:** 2026-06-24
**Track:** mechanical-kit
**Verdict:** works

## Goal

First mechanical-kit deliverable: Sounding's rover `Part` catalog (WI 608) as glb — tire, rim,
suspension, seat, antenna, solar panel, bumper — generated in asset-harness for the Sounding session
to retrieve and integrate (Sounding is under active development elsewhere; **no Sounding-repo edits**).

## Tooling

- **Blender 4.0.2 headless on `ai2`** (SSH) — [`prototypes/blender_parts.py`](../prototypes/blender_parts.py)
  builds each part parametrically (bpy primitives + bevel modifier), sets origin to the mount point,
  exports `.glb`. Preview via [`prototypes/render_parts_preview.py`](../prototypes/render_parts_preview.py)
  (EEVEE).
- No image-to-3D, no ComfyUI for the geometry. Surfaces are embedded PBR factors (v1).

## Licensing

Fully clean: Blender (GPL — outputs are yours) + our parametric geometry. The clean 3D lane — none of
the Hunyuan community-license baggage the `3d-static-props` hero path hit.

## Export contract (from `crates/sim/src/{voxel,rover}.rs`)

- Frame **+Y up / +Z forward / +X axle**; steering about +Y (rover.rs: "world +Z is the rover's
  forward", steer about the up axis).
- **Origin = mount point** (`Part.mount`, metres, lattice frame); identity rotation drops the part in
  place. **glTF Y-up.** `cell_size`-parameterised (reference 0.5 m; `--cell-size` scales linearly).
- A wheel station = **Suspension + Rim + Tire** sharing the hub-centre mount (WI 630).
- Full per-part contract in [`../parts/manifest.json`](../parts/manifest.json).

## Result

- **Outputs (committed for retrieval):** [`../parts/`](../parts/) — 7 `.glb` + `manifest.json` +
  README. Preview: [`samples-2026-06-24/parts_contact_sheet.png`](samples-2026-06-24/parts_contact_sheet.png).
- **Verification:** EEVEE renders confirm all seven are recognisable and correctly oriented (tire =
  rubber disc on X; rim = metal hub; suspension = vertical strut + chassis plate; seat = pad+back
  facing +Z; antenna = mast on +Y; solar = blue panel normal +Y; bumper = lateral bar). Vert counts
  48–610 (low, glTF-clean, uncompressed — Bevy-friendly). Can't load in Sounding this pass (active
  there); render is the verification.

## Repeatability

- Deterministic (no RNG). One Blender launch builds all parts + manifest. `cell_size` is a CLI flag.

## Next

- **AI-textured surfaces** via `pbr-materials` (UV-unwrap + bake albedo/normal/roughness/AO) — v1 uses
  flat material factors; this is the "AI surface" half of the track's premise.
- **Decals/greebles** for variety (parts can read samey).
- Confirm exact part **orientation** against Sounding's WI 608 importer when it lands; adjust origins
  if the rover assembly expects a different per-part convention.
- **Rocket-domain catalog** (fuel tank, engine bell, nose cone, fins, decoupler) as the second set.
