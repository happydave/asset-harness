# Findings: the lane on ComfyUI v0.37.2, and Pixal3D multi-view on gfx1151

**Date:** 2026-09-23 · **Work item:** WI 1751 (tickets) · **Host:** `gtr`, Radeon 8060S (gfx1151) ·
**Image:** `localhost/wi1600-comfyui:0.37.2` (`c5db1a05a18c`) · **Checkout:** v0.37.2 (`830232b8`)

## Verdicts

- **Pixal3D multi-view runs on gfx1151 and gives a recognisable textured asset.**
  - The shipped `3d_pixal3d_multi_views.json` ran on its own example sheet (a four-view character
    turnaround, 6336×2688) with both guards, and finished textured in 1,500 s.
  - From every side, the mesh follows the sheet's four views: helmet antennae, shoulder armour,
    chest ring, arm and leg plating, and the white-and-grey scheme.
  - The texture is softer than the sheet, and small accents are mostly lost. The asset is posed
    facing a different axis from the renderer's 0°.
  - No black or magenta regions.
  - One input, one seed. `samples-2026-09-23/multiview_character_v0372.png` shows the sheet beside
    three renders.
- **The single-image template still works, unchanged.**
  - The template shipped in templates 0.11.69 is byte-identical to 0.11.55's.
  - Both arms finished textured (TRELLIS.2 1,831 s; Pixal3D 1,040 s), and the crates follow the
    input as on v0.34.6.
- **Both guards still apply.**
  - The GEMM guard's target (`SparseLinear`) is unchanged. The decode gate passes with 6,481,978
    vertices, twice. That is +88 against v0.34.6 on this host and inside the gate's ±648, and it is
    gtr's v0.37.2 reference.
  - `parameterize.py` is unchanged, and the unwrap guard's fallback fired once in each of the three
    runs.
  - The GEMM guard's negative control needs gfx1201 and moved to WI 1767 (`ai2`).
- **Peaks are lower than on v0.34.6**, with numba in both images, from an empty pool:
  - TRELLIS.2 22.8 GB (25.9 on v0.34.6);
  - Pixal3D 18.5 GB (22.8);
  - multi-view 17.1 GB.

  The lowest `MemAvailable` in any run was 79.5 GiB. One run each (descriptive).

## Multi-view input rules (from the node and the template)

- `Pixal3DMultiViewConditioning` takes up to four square views: front, left, back and right, 90°
  apart. Each has alpha or a black background, the object spans about 1/1.1 of the frame at its
  widest, and every view has the same scale. `fov` is 20 for rig renders and most multi-view
  generators.
- The template cuts one sheet with four **fixed pixel boxes** (`ImageCropV2`: x = 0, 1652, 3182, 4728;
  height 2688). A sheet of any other geometry needs its boxes edited, or the views wired in
  directly.
- There is no crate turnaround yet. The owner decides where one comes from (WI 1751, O1).

## Converter changes (`template_to_api.py`)

- `--default Type.input`: a widget a newer server added at the end of a node's list takes its schema
  default, and each fill is reported. v0.37.2's `MoGeInference.refine_steps` (MoGe-3 only) needs it.
  Without the flag the conversion stops, because a widget inserted mid-list would look the same.
- `BOUNDING_BOX` widgets (`ImageCropV2`) are taken as the region dict. The crop component's four
  trailing integers are skipped, and anything else is refused.
- An output node's own non-default prefix becomes a suffix (`<prefix>_front_view`), so the view crops
  keep their names.
- `convert` no longer writes overrides into the caller's template.
- A regression test pins both single-image arms to the graphs WI 1761 ran
  (`test_template_to_api.py`, 13 checks).
