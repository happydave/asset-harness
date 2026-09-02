# Findings: "we live in a world of magic" Slack emoji

**Date:** 2026-09-01
**Track:** 2d
**Verdict:** works

## Goal

Produce a set of static Slack custom emoji expressing "we live in a world of magic" — the reaction
for something working impossibly well — and, in doing so, point the 2d harness at a **new kind of
target**: tiny, symbolic, displayed at roughly a fifth of the size it is stored at. The output is a
media artifact, not a game asset, the same bounded exception the music-video track carries.

The durable outputs are the [Slack delivery-target spec](../../docs/delivery-targets/slack-emoji.md)
and the two matte rules below; the images are the occasion, not the point.

## Tooling

- **Base model:** Z-Image `base` (`z_image_bf16.safetensors`), text encoder `qwen_3_4b` (type
  `lumina2`), VAE `ae.safetensors`
- **LoRA(s) / ControlNet / adapters:** none — txt2img only. No ControlNet: an emoji has no posed
  structure to steer, and the Turbo-trained ControlNet does not transfer to `base` (WI 924).
- **Matting:** `BiRefNet-HR-matting.safetensors` via `RemoveBackground` → `InvertMask` →
  `JoinImageWithAlpha`
- **Workflow / nodes:** [`2d/prototypes/generate_emoji.py`](../prototypes/generate_emoji.py) (graph
  built in code, ComfyUI API), [`emoji_post.py`](../prototypes/emoji_post.py) (PIL post + spec gate +
  contact sheet), [`comfy_client.py`](../prototypes/comfy_client.py) (WI 1020 job waiting)
- **Other software:** Pillow; stdlib + `requests`

## Licensing (commercial / redistribution)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| Z-Image base | Apache-2.0 | yes | yes | Tongyi Z-Image |
| BiRefNet-HR-matting | MIT | yes | yes | BiRefNet |

- **Effective output license:** Apache-2.0 (most restrictive link)
- **Safe for a clean/commercial asset pack?** yes
- **Notes:** Prompt hygiene per [`music-video/license-lane.md`](../../music-video/license-lane.md) was
  a live constraint rather than a formality here: the stock cultural imagery of "magic" is largely
  franchise wizards. Every direction was written around generic objects — a hat, a wand, a hand, a
  mug, a circuit board — with no franchise, character, or named-work reference in any prompt.

## Hardware

- **Machine / GPU:** `ai2`, gfx1201 (R9700), 31.9 GiB VRAM
- **Stack:** ROCm 7.2.4, ComfyUI. ~40 s per candidate at 1024 × 1024, 20 steps. No configuration
  change was made to the shared service.

## Inputs

- **Style anchor:** `a small flat vector icon, centered on a large plain white background, generous
  empty white space around it, thick dark outline, bold saturated colors, strong high contrast,
  minimal internal detail, one single subject`
- **Negative:** text/lettering guard + `pale washed out colors, white fill, full-bleed background,
  thin delicate lines, fine intricate detail`
- **Directions:** 5 distinct readings of the sentiment (`hat-on-laptop`, `hand-sparkles`,
  `hat-and-wand`, `glowing-object`, `circuit-bloom`), plus one corrective re-run
  (`hat-and-wand-bright`)
- **Seeds:** 11, 22, 33 per direction (11, 22 for the corrective run)
- **Key params:** 20 steps, cfg 4.0, euler / simple, ModelSamplingAuraFlow shift 3.0, 1024 × 1024
- Per-candidate recipes (prompt, seed, sampler settings, model artifacts, full graph) are committed
  beside the samples.

## Steps

1. `python3 generate_emoji.py --out outputs/emoji` — 5 directions × 3 seeds, RGBA + opaque render +
   recipe per candidate.
2. `python3 emoji_post.py build outputs/emoji --out outputs/emoji128` — trim to the alpha bbox, scale
   down to fit, centre on a 128 × 128 transparent canvas.
3. `python3 emoji_post.py check outputs/emoji128` — the spec gate.
4. `python3 emoji_post.py sheet <passing> --out sheet.png` — 16/22/32 px on light and dark.
5. Judge the sheet at display size; cut what does not read; re-run any direction the judgement
   condemns for a fixable reason.

## Result

- **Sample output(s):** [`samples-2026-09-01-world-of-magic/`](samples-2026-09-01-world-of-magic/) —
  the 6 delivered emoji and their recipes in
  [`emoji/`](samples-2026-09-01-world-of-magic/emoji/) (so
  `emoji_post.py check <that dir>` runs clean), with the
  [contact sheet](samples-2026-09-01-world-of-magic/contact-sheet.png) and one
  [matte-failure exhibit](samples-2026-09-01-world-of-magic/matte-failure-pale-subject.png) beside it.
- **Delivered:** 6 files across 5 distinct readings, 18–37 KB each (the cap is 128 KB), every one
  square, 128 × 128, with a real alpha channel.
- **Yield:** 17 candidates generated, 14 passed the automated spec gate, 6 survived inspection at
  display size. The gate is a floor, not a selector — see below.

### What worked

- The **whole pipeline is cheap**: ~40 s per candidate, and the post-processing is instant. Generating
  a variety and throwing most of it away is the correct way to work here.
- **Reproducibility is exact.** Replaying a delivered candidate's recorded recipe reproduced it
  **pixel-identically** (difference bbox `None`), so the recipe record is complete.
- The **display-size contact sheet did the real work.** Every candidate looked acceptable at 128 px;
  the sheet is what separated them.

### What failed, and why it was useful

Three failure modes, each of which changed the tooling or the guidance:

1. **Full-bleed art defeats matting entirely.** The first candidate came back with alpha maxing at
   20/255. Saving BiRefNet's raw mask showed it was near-zero everywhere: the prompt had produced
   edge-to-edge artwork, and a salient-object matting model given no background finds no object. The
   inherited `InvertMask` polarity was never wrong. **Fix:** the style anchor must demand a *small*
   subject inside a large white frame.
2. **A pale subject on white is unmattable.** Of three prompt variants, the one phrased "thick white
   die-cut border" came back semi-transparent *through the subject*, and the one whose fill went
   white kept **only the dark outlines** — the entire interior went transparent
   ([exhibit](samples-2026-09-01-world-of-magic/matte-failure-pale-subject.png)). **Fix:** saturated
   colours in the style anchor, strong colours named per direction, and `pale washed out colors,
   white fill` in the negative.
3. **A dark subject fails on Slack's dark theme.** The black top hat is the *clearest* candidate in
   the set at 22 px on white and an unreadable blob at 22 px on dark. Regenerating the same
   composition in bright purple with a gold band fixed it outright, and that corrected version is in
   the delivered set. This one is invisible unless both backgrounds are checked, which is why the
   contact sheet renders both.

**The automated gate passed images the eye rejects, twice.** `hat-and-wand_s33` is 39 % opaque and
passes every mechanical check while being a near-white wisp; `hat-and-wand-bright_s11` likewise. A
shape-and-bytes gate cannot know whether a picture is *there* — it is a floor that catches blanks and
malformed files, and inspection is the actual selection step. This is the 2d-track instance of
`skills/evidence.md`'s "inspect the artifact, not just the metric".

## Repeatability

- **Deterministic given seed:** yes — verified by replay, pixel-identical on the same host and graph.
- **Style-consistent across runs:** yes within a direction; the style anchor holds the look together
  across directions without a LoRA, as elsewhere in this track.
- **Manual cleanup required:** none. No candidate was hand-edited; the ones that failed were cut and,
  where the cause was understood, re-generated with a corrected prompt.

## Next

- **Owner step:** pick from the delivered set and upload as `:world-of-magic:` (lower-case is a
  confirmed Slack rule; if the hyphen is refused, `world_of_magic` is the fallback).
- **WI 1238 — animated GIF emoji** (tracked in the tickets repo; no cross-repo link, per the repo's
  link hygiene). It consumes the delivery-target spec's animated section rather than re-deriving it.
  The
  open question there is whether Wan2.2 i2v suits a ~20 px looping icon at all, or whether
  frame-authored animation is both cheaper and better-suited.
- **Not folded into the harness:** the emoji style anchor is deliberately local to
  `generate_emoji.py`. One sentiment's worth of candidates is not enough to claim a house emoji
  style; a second emoji job would be the evidence for that.
