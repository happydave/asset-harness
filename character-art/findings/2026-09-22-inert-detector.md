# The inert-detector check compared bytes, and two of four face passes had done nothing

**WI 1732** · 2026-09-22 · corrects part of [2026-09-20-harness-prototype.md](2026-09-20-harness-prototype.md)

## What was wrong

The harness's inert-detector check (WI 1611 Invariant 4: a detail pass whose detector did not fire
is a failure, not a no-op) compared SHA-256 digests of the two stage files. ComfyUI's `SaveImage`
writes each stage's own graph into the PNG's `tEXt` chunk, so the output of a pass that changed
nothing still differs from its input in bytes. The check could not fire in production, and the
record said `changed: true` for every stage of every character.

Re-judged by decoded pixels (`compare_stages.py` over the WI 1611 run root):

| Character | face pass | every other stage |
|---|---|---|
| dragonborn | **pixel-identical to its input** | changed |
| half-orc | **pixel-identical to its input** | changed |
| human | changed | changed |
| tiefling | changed | changed |

So the earlier findings document's "Dragonborn … visibly crisper" and "Half-orc … tusks better
defined" were the work of the upscale, hand, and house-style passes, not of the face pass; its
F-t3 ("the anime face detector fired on the dragonborn") is **refuted**. Confidence: Confirmed —
the artifacts themselves, one seed per character.

## Why the pixels were unchanged: the detector found nothing

Impact Pack's `FaceDetailer` returns its input tensor and an all-zero mask when its detector
returns no segments. Run live with the mask saved beside the image:

| Probe on the `upscale` derivative | `yolov8_animeface` (the track's face detector) | `face_yolov8m` (general, also installed) |
|---|---|---|
| dragonborn | mask all zero → **found nothing** | found nothing |
| half-orc | mask all zero → **found nothing** | **found the face** (pixels changed) |
| human (control) | found the face (mask over the head), pixels changed | — |

One seed each. The dragonborn's draconic head is missed by both detectors; the half-orc's is missed
by the anime one and found by the general one. Detector choice is not this work item's to change;
the observation is here for the track. WI 1611's plan predicted exactly this edge case ("a
dragonborn is the likely case") and asked for it to be recorded on the record as a skip,
distinguishable from an absent detector — which the harness now does.

## What the harness does now

- **Pixels, not bytes.** `chain.is_inert` decodes both images and compares mode, size and raw
  pixels; a non-image raises.
- **The detail graph saves the detector's mask** (`MaskToImage` → `SaveImage`, prefix `…_mask`).
  The driver reads it: any lit pixel means detected.
- **Four cells, one pure decision** (`chain.detail_verdict`): detected + changed → pass; nothing
  detected + unchanged → **skip**, recorded, run continues; detected + unchanged → **fail** (the
  inert detector); nothing detected + changed → fail (not a detail pass). Applied to the face **and
  hand** stages. Each stage record carries `detected`, `pixels_changed`, `outcome`, `reason`.
- **Re-runs work.** An existing master is reused after its embedded seed and prompt are checked
  against the roster row; derivatives, tokens and `records.json` of a re-run go to `.2.` (then
  `.3.`…) paths beside the first run's; the guard's refusal is a character failure, not an abort.
- `compare_stages.py` re-judges any run root read-only; `probe_detail.py` runs one detail pass and
  prints its cell. Both were used to produce the tables above.

## Bounds

Four characters, one seed each; the round trip's pixel-exactness rests on those pairs plus the
code path (`/255.0` in, `255.*` then `uint8` out), which is Supported, not proven for every value.
No detector threshold was swept.
