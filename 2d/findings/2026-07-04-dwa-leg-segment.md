# Findings: DWA spider-miner leg-segment sprite

**Date:** 2026-07-04
**Track:** 2d
**Verdict:** works

## Goal

Produce the DWA WI 801 spider-miner **leg-segment** sprite for DWA WI 818 — one reusable,
directional limb segment that DWA WI 817 stretches along each rig segment (root→knee, knee→tip)
and rotates into pose, replacing the procedural vector-stroke legs. Companion to WI 813 (the
radially-symmetric body); same fleet STYLE anchor + seed family so the leg reads as the same
machine. Several candidates were generated for Dave to choose from.

## Tooling

Identical clean stack to WI 813 (Z-Image Turbo + Z-Image Fun ControlNet Union 2.1 via Canny +
BiRefNet-HR matting; no LoRAs/finetunes). Scripts:
`2d/prototypes/make_primitives.py::leg_segment` (control primitive),
`2d/prototypes/generate_leg_segment.py` (candidate sweep + contact sheet, mirrors
`generate_spider_miner.py`), `2d/prototypes/build_atlas.py` (trim + atlas).

## Licensing (commercial / redistribution)

Same all-Apache/MIT chain as WI 813 → **effective output license Apache 2.0**, clean by
construction (no LoRAs/finetunes), safe for a commercial asset pack. (AI-generated images may
not be copyrightable in some jurisdictions — affects claiming the output, not using the model.)

## Hardware

`ai2` — gfx1201 (R9700 spare card); ROCm; ComfyUI at `http://ai2:8188/`.

## Inputs

- **Prompt:** shared `STYLE` anchor + subject: "a single articulated mechanical leg segment of an
  asteroid-mining spider drone, shown flat in orthographic side view, an elongated tapered
  armored limb with a round pivot joint at the left end and a pointed rotary drill tip at the
  right end, the lower inner edge lined with rock-cutting drill teeth and chainsaw blades, heavy
  weathered industrial machinery, isolated".
- **Control primitive:** `make_primitives.leg_segment` — a horizontal tapered bar, round pivot
  knuckle (left) → drill point (right), a row of triangular teeth on the bottom edge, panel
  lines on top. High-contrast for Canny; ControlNet strength 0.85 locks the geometry.
- **Seeds:** base `729703840979498` (shipped-fleet + WI 813 body family) + `i·101` for i in
  0..5 → cand00..cand05. **Chosen: cand03, seed `729703840979801`.**
- **Key params:** 8 steps, cfg 1.0, res_multistep / simple, AuraFlow shift 3.0, ControlNet
  strength 0.85, primitive Canny.

## Steps

1. `python make_primitives.py leg_segment inputs` — writes the control primitive.
2. `python generate_leg_segment.py --count 6` — sweeps 6 seeds, writes RGBA/opaque/canny per
   candidate, a manifest, and `contact_sheet.png`.
3. Pick cand03, then
   `python build_atlas.py --manifest outputs/leg_segment/chosen_manifest.json --indir
   outputs/leg_segment --outdir outputs/leg_segment/atlas --name dwa_miner_leg --max-dim 256`
   → atlas PNG + Phaser JSON, single frame keyed `leg_segment`.

## Result

- **Sample output(s):** `2d/findings/samples-2026-07-04-leg-segment/` — the chosen sprite
  (`leg_segment.png`, 256×88), the atlas (`dwa_miner_leg.png` + `dwa_miner_leg.json`, frame
  `leg_segment`), and `contact_sheet.png` of all six candidates. (Bulk `outputs/` git-ignored.)
- **What worked:** all six read as coherent tapered limb segments with a round pivot knuckle, a
  drill tip, and a toothed inner edge, in the fleet palette — coherent with the WI 813 body via
  the shared STYLE anchor + seed family. The directional (non-symmetric) subject + a directional
  control primitive held the pivot-left / drill-right / teeth-bottom layout. cand03 has the
  cleanest concentric pivot, evenest teeth, and a sharp tip (best for the WI 817 stretch/rotate).
- **What failed / artifacts:** none blocking; `build_atlas` `--alpha-threshold 8` (default)
  trims the BiRefNet matte cleanly.

## WI 817 render contract (the integration surface)

- **Frame:** `leg_segment` in atlas `dwa_miner_leg` (256×88).
- **Orientation:** long axis = +x. **Pivot** (rotation origin, the knuckle centre) ≈
  `(0.18·w, 0.50·h)` — i.e. Phaser `setOrigin(0.18, 0.5)`; place at the rig segment's proximal
  end (root or knee), rotate to the segment angle, scale x to `segmentLength / naturalLength`.
- **Inner tool edge = bottom (+y)** in the source; WI 817 orients/flips so the teeth face the
  rock (the rig knows the inward side).
- **Palette:** fleet gunmetal + rust-orange, matching WI 813.

## Next

- DWA WI 817 renders this frame per rig segment (front/back split from WI 819 already in place),
  replacing the vector strokes; coordinate any pivot/aspect tweaks against this contract.
- Optional: a distinct `leg_upper` (no drill tip) if the single-segment reuse reads oddly on the
  proximal segment — a follow-up sweep, not needed for the first integration.
