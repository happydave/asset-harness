# character-art harness

Turns a roster CSV into VTT-ready tokens through the finishing chain. Built for WI 1611 against
`design-character-art.md`; findings at `../../findings/2026-09-20-harness-prototype.md`, corrected
by `../../findings/2026-09-22-inert-detector.md` (WI 1732).

```
python3 run_batch.py --roster ../../roster/cast.csv --root out \
                     --input-dir <ComfyUI input dir> --server http://127.0.0.1:7124
```

## The roster is the point

One CSV row per character. WI 1611 calls it "simultaneously the prompt source, the campaign roster
and the regeneration key, and more valuable than any individual image" — the images are
reproducible from it, so it is the artifact worth keeping.

`identity_features` is load-bearing and semicolon-separated. It is the track's **test oracle**: the
features named there are what a preservation check is run against. **A row without them is not
deliverable** and the harness says so rather than generating it, because there would be nothing to
check the result against.

## The master rule is enforced, not remembered

A master PNG carries its own ComfyUI workflow in its `tEXt` chunks, so destroying one destroys the
recipe. `provenance.may_write(dest, role)` is a **pure predicate** — it reads and never writes —
and `write_guarded` is the only writer. Masters are marked two independent ways (the `masters/`
directory and the `.master.png` suffix) so a misrouted derivative is caught either way.

`test_provenance.py` passes real master paths to the predicate directly and only ever hands the
writer paths it created in a temp dir. The guard's refusal branch has been disabled once and the
test observed to fail — a guard whose test has never failed proves nothing.

## Detail stages are judged by pixels and by the detector's mask

Each detail graph saves two images: the detailed picture and the `FaceDetailer`'s mask (prefix
`…_mask`). The driver decides the stage from two booleans — did the mask light up, did the pixels
change — through `chain.detail_verdict`:

| detected | pixels changed | outcome |
|---|---|---|
| yes | yes | pass |
| no | no | **skip** — recorded on the stage entry, the run continues (a dragonborn's head under the anime detector) |
| yes | no | **fail** — the inert detector |
| no | yes | fail — whatever ran was not the detail pass |

Pixels, never file bytes: ComfyUI embeds each stage's graph in the PNG, so two files with the same
picture never have the same bytes. Face and hand stages both go through this.

## Re-runs

Running again into an existing `--root` reuses each master (after checking the seed and prompt it
carries against the roster row — a mismatch fails that character) and writes every new derivative,
token and the records file to `<name>.2.<ext>` beside the first run's. Masters are never
regenerated or overwritten.

## Tests and tools

Plain `python3`, no pytest, non-zero exit on failure — the track's convention.

```
python3 test_provenance.py   # the master guard
python3 test_roster.py       # loading, validation, the not-deliverable rule
python3 test_tokens.py       # sizes, formats, the no-baked-border rule, alpha polarity
python3 test_chain.py        # pixel comparison, mask reading, the four-cell verdict, graph shape, matte polarity
python3 test_run_batch.py    # the driver against a fake ComfyUI: verdicts, re-run, failure paths

python3 compare_stages.py --root <run root>   # re-judge an existing run by pixels, read-only
python3 probe_detail.py --server … --input-dir … --image … --detector face --prompt … --seed … --out …
```

A token-suite fixture must be **RGBA with a transparent background**. An RGB source is promoted to
alpha 255 everywhere, and every polarity assertion then passes vacuously.

## Traps

- **`CLIPSetLastLayer -2` is mandatory** on Illustrious/Pony and fails *silently* when omitted.
- **A `FaceDetailer` whose detector finds nothing, or never loaded, is silently inert** — it runs,
  reports success and returns its input. Only the mask tells the two apart; the driver reads it
  and fails on found-but-unchanged. Comparing file bytes cannot see either case (WI 1732).
- **Never point the detail pass at InsightFace.** Every ArcFace-family method either fails to
  detect a dragonborn or silently erodes its snout toward a human face. The YOLO bbox detectors
  here need no identity embedding.
- **`RemoveBackground` and `JoinImageWithAlpha` disagree about what a MASK is.** The first emits a
  *foreground* mask; the second follows ComfyUI's convention that a mask marks what is masked out,
  and computes `alpha = 1.0 - mask`. Wired directly the negations compose and the figure becomes
  the hole — which is what shipped, in every matte and every token, until WI 1636. An `InvertMask`
  between them is the fix, and `chain.figure_is_opaque` refuses the output if it ever returns.
- **Impact Pack needs `segment-anything` but not `sam2`** — see the findings.
