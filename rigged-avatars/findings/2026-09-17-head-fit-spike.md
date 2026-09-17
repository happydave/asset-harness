# Findings: spike — fit the parametric head to a reference still

**Date:** 2026-09-17
**Track:** rigged-avatars
**Verdict:** partial — the idea survives, the fitter is not worth cutting yet: nothing tested reads a stylized face, and the head's constants are absolute where they need to be relative

## Goal

Decide whether to build landmark-driven fitting of the stylized head's parameters to a generated still, so a
character liked as a 2d still is "born rigged" (asset-harness WI 1371). A spike: throwaway tools, one verdict.

## Tooling

- MediaPipe FaceLandmarker (`tasks-vision` 0.10.14, Apache-2.0 code and weights) in headless Chromium, from
  `prototypes/obs_page/vendor/`. [`spikes/head_fit/detect.py`](../prototypes/spikes/head_fit/detect.py).
- A prior-free reader of flat-shaded faces, [`blobs.py`](../prototypes/spikes/head_fit/blobs.py): the face is
  the connected skin region, the features are its holes.
- [`head_render.py`](../prototypes/spikes/head_fit/head_render.py): imports the production generator, overrides
  its constants, renders front-on (ten 512 px renders in 13 s on ai2) and can run the generator's full checks.
- References: two committed clean-lane stills, `2d/findings/samples-2026-07-14-zanime/txt2img_zanime.png` and
  `2d/findings/samples-2026-07-14/txt2img_base_anime.png`. No GPU generation was run.

## Licensing (commercial / redistribution)

Nothing shipped. Tools only, all already in the repo's clean lane.

## Results

**MediaPipe's gain on our own renders** — one constant moved at a time, detected change ÷ true change:

| mouth height | mouth width | face width | eye line | face length | eye spacing | eye opening | eye width | brow height |
|---|---|---|---|---|---|---|---|---|
| 1.00 | 0.82 | 0.68 | 0.59 | 0.35 | 0.30 | 0.05 | −0.02 | −0.19 |

It measures a mouth and imposes a human face on the rest. On the chibi still it reports one face and puts the
mouth markers on the nose ([`overlay1.png`](samples-2026-09-17-head-fit-spike/overlay1.png)). Closed as a
source for fitting; still right for what `obs_page` uses it for.

**The hole-reader** gets the eyes and mouth of the flat Z-Anime still, stably across tolerances — and got the
mouth *wrong*, boxing one of the two strokes the still draws it with
([`blobs_refs.png`](samples-2026-09-17-head-fit-spike/blobs_refs.png)). It finds no face outline there, and
fails on the chibi still and on our own shaded render.

**Our side needs no reader and no render loop:** the head's constants are its landmark positions, so fitting
is closed-form once something reads the reference. The optimiser is not the hard part.

**One fit, to the Z-Anime proportions** (eye opening 38 → 72 mm, mouth 28 mm nearer the eye line): the
generator refuses to build (three fixed 8 mm insets overrun the mouth patch), then with the inset thinned
builds and fails 5 of 105 checks and 1 gate row — the eyeball no longer fits its aperture, and `mouthClose`
misses an absolute-millimetre floor. [`side_by_side.png`](samples-2026-09-17-head-fit-spike/side_by_side.png):
the proportions move the right way; the eyes are a hollow socket or a ball through the shell.

## Next

- WI 1529 — make the head's dependent constants scale-relative; its test case is
  [`jobs_fit.json`](samples-2026-09-17-head-fit-spike/jobs_fit.json).
- After that, a small spike on a vision-language model as the stylized-face reader, with the gain table above
  as the bar and `blobs.py` as the baseline.
