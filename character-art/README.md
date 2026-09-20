# character-art

Generation of **character assets**: portraits and profile pictures, reference / turnaround sheets,
VTT tokens, group shots. The asset class is characters; the first consumer is the D&D campaign
(`dnd-platform`), but the track is scoped as an asset class rather than as one campaign's lane.

Track opened 2026-09-19 from the WI 1591 research series (six rounds, archived in the tickets repo
under `docs/projects/asset-harness/research/`). Start with the digest:
`docs/pending/1591-ah-dnd-character-art-research/discover.md`.

## Boundary with other tracks

- **`2d`** owns backdrops, scenery and tiling textures. Environment and interior work for a campaign
  belongs there, not here — this track stops at the character.
- **`rigged-avatars`** owns rigging, VRM and animation. A mesh lifted from a character portrait is a
  hand-off to that track, not work for this one.
- **`3d-static-props`** owns image-to-3D. Character meshes use its tooling; the portrait that feeds
  them comes from here.

## The architecture (designed and approved, 2026-09-19 — WI 1598)

**Split generation lane, single finishing lane.** The design lives in the tickets repo at
`docs/projects/asset-harness/design-character-art.md`; a working implementation of it is at
[`prototypes/harness/`](prototypes/harness/), with findings in
[`findings/2026-09-20-harness-prototype.md`](findings/2026-09-20-harness-prototype.md).

| Lane | Model | Why |
|---|---|---|
| Characters, tokens, sheets | SDXL booru-tag checkpoint | Framing and body-attribute tags are a precision instrument; `multiple_views` is a 272k-example token no prose model has an equivalent for |
| Environments, interiors, text | Z-Image | Natural-language encoder; the only family in scope that renders legible text |
| Re-projection (turnarounds, new angles, LoRA datasets) | Qwen-Image-Edit-2511 | Apache-2.0; the only candidate with a published Apache turnaround LoRA. **Measured 2026-09-19 (WI 1599): it preserves non-human race features** — nothing was humanised across 11 runs, and base 2511 re-pose needs no turnaround LoRA at all |
| **Finishing — every image from every lane** | one nominated house-style model + one house-style LoRA, img2img at **denoise 0.20–0.30** | Coherence is a *rendering* problem, not a generation one. One dataset, one style LoRA |

## Model lanes and licence

Per the owner decision of 2026-09-19 (see tickets WI 1594):

- **Clean lane (anything that could ship): Illustrious XL v1.1.** It declares OpenRAIL++-M explicitly
  with a `license_link` to the canonical text. v2.0 declares a bare `creativeml-openrail-m` tag that
  Onoma's own prose contradicts and that Onoma has never answered.
- **Personal lane (non-commercial campaign use): Illustrious XL v2.0**, and the campaign-lane
  comparators — WAI-illustrious v17, Pony V6 with `source_furry` for non-human races.
- **No Onoma repository has ever contained a `LICENSE` file.** Archive the **model-card revision
  hash** plus the linked upstream licence text. Current pins: `8d966ec` (v1.1), `69459c1` (v2.0),
  `89d6254` (v1.0), all 2025-04-19.
- **Illustrious v3.x is not an open-weights line** — no v3.x repository exists in the Onoma org.

## Standing traps

- **Never install InsightFace for this track.** Every ArcFace-based identity method fails in
  principle on non-human faces; the detail pass uses a furry/anime YOLO bbox detector instead.
- **Impact Subpack is a separate install** — a FaceDetailer without `UltralyticsDetectorProvider` is
  silently inert.
- **Clip skip 2** on Pony and Illustrious; a graph missing `CLIPSetLastLayer -2` fails quietly.
- **Check tag post counts before designing a recipe**: `danbooru.donmai.us/tags.json`. `front_view`
  and `dragonborn` do not exist; `character_sheet` is dead; bare `bow` is a hair ribbon.
- **The raw PNG out of ComfyUI is the master and is never overwritten** — it carries the workflow in
  its `tEXt` chunks, and a WebP token export strips it.
