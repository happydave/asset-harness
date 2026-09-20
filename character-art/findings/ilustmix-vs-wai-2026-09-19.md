# Findings: IlustMix v9 vs WAI-Illustrious v17 for the character lane

**Date:** 2026-09-19
**Track:** character-art
**Verdict:** partial — IlustMix wins on the owner's stated axes, with one named caveat

## Goal

Owner direction (2026-09-19): try `ilustmix_v9` alongside the checkpoint WI 1599 generated its
source portraits with, on the read that it is "similar to illustrious but less cartoonish and
better detail". Evidence for WI 1598 (`tickets/docs/pending/1598-ah-character-art-track-design/workitem.md`)'s
choice of generation-lane checkpoint. **No decision is recorded here** — the choice is WI 1598's.

It bears on architecture, not taste: if the generation lane arrives closer to the house style on its
own, the finishing lane has less to carry.

## Tooling

- **Checkpoints:** `ilustmix_v9.safetensors` vs `waiIllustriousSDXL_v170.safetensors`, both already
  installed on `ai2`'s shared ComfyUI
- **Everything else held constant:** same prompts, same seeds (tiefling 303, dragonborn 404,
  half-orc 202, human 202), CLIP skip −2, dpmpp_2m/karras, 30 steps, CFG 5.0, 768×1344. The
  checkpoint is the only variable.
- **Script:** `../prototypes/qwen-edit-2511/gen_portraits.py` with `CKPT` overridden
- 4 images in 35 s on the shared service (queue empty before and after; service used, not modified)

## Result

**The owner's read is confirmed, consistently across all four subjects.** IlustMix is less
cartoonish and carries more detail: more natural anatomy and proportion, painterly rather than flat
cel shading, more material detail in leather and metal, and faces that are semi-realistic rather
than anime. WAI's outputs read as stylised game characters; IlustMix's read as concept art.

**But race-feature legibility — which is what this track actually needs — splits three ways:**

| Subject | Feature | Which checkpoint reads better |
|---|---|---|
| Dragonborn | snout, scales | **IlustMix, clearly.** More dramatic and far crisper — defined teeth, sharper scale texture, more articulated horns |
| Tiefling | horns | **Comparable.** IlustMix's are glossier and better shaped; both unambiguous |
| Half-orc | tusks | **WAI.** IlustMix's tusks come out noticeably smaller and thinner against a more human-proportioned jaw |

That last row is the caveat, and it is not cosmetic. WI 1599 established that the edit model
preserves what is **legible in the source** — discrete, high-contrast, silhouette-level features
survive re-projection; faint ones have less to survive on. A checkpoint that renders smaller tusks
hands the whole downstream pipeline less to hold.

It is also probably fixable in prompting rather than by rejecting the checkpoint: strengthen the
tusk tags and weights when generating orcs on IlustMix, and re-check. That was out of scope here —
this SideQuest holds every variable but the checkpoint.

## Licensing

Unchanged and still open: `ilustmix_v9` is a third-party Illustrious **merge**, like
`waiIllustriousSDXL_v170`. Neither resolves against WI 1594's clean-vs-personal split as written.
See the track README and WI 1598 — swapping one merge for another does not settle it.

## Samples

- `ilustmix-vs-wai-2026-09-19/side_by_side_full_figure.png` — all four subjects, WAI left, IlustMix right
- `ilustmix-vs-wai-2026-09-19/side_by_side_heads.png` — the feature-legibility comparison
- `ilustmix-vs-wai-2026-09-19/ilustmix_*.png` — the four IlustMix generations at full size
