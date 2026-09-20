# character-art harness

Turns a roster CSV into VTT-ready tokens through the finishing chain. Built for WI 1611 against
`design-character-art.md`; findings at `../../findings/2026-09-20-harness-prototype.md`.

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

## Tests

Plain `python3`, no pytest, non-zero exit on failure — the track's convention.

```
python3 test_provenance.py   # the master guard
python3 test_roster.py       # loading, validation, the not-deliverable rule
python3 test_tokens.py       # sizes, formats, the no-baked-border rule, alpha polarity
python3 test_chain.py        # the inert-detector and matte-polarity decisions, and graph shape
```

A token-suite fixture must be **RGBA with a transparent background**. An RGB source is promoted to
alpha 255 everywhere, and every polarity assertion then passes vacuously.

## Traps

- **`CLIPSetLastLayer -2` is mandatory** on Illustrious/Pony and fails *silently* when omitted.
- **A `FaceDetailer` without a loaded `UltralyticsDetectorProvider` is silently inert** — it runs,
  reports success and changes nothing. The driver diffs each detail stage against its input and
  fails on a bit-identical result.
- **Never point the detail pass at InsightFace.** Every ArcFace-family method either fails to
  detect a dragonborn or silently erodes its snout toward a human face. The YOLO bbox detectors
  here need no identity embedding.
- **`RemoveBackground` and `JoinImageWithAlpha` disagree about what a MASK is.** The first emits a
  *foreground* mask; the second follows ComfyUI's convention that a mask marks what is masked out,
  and computes `alpha = 1.0 - mask`. Wired directly the negations compose and the figure becomes
  the hole — which is what shipped, in every matte and every token, until WI 1636. An `InvertMask`
  between them is the fix, and `chain.figure_is_opaque` refuses the output if it ever returns.
- **Impact Pack needs `segment-anything` but not `sam2`** — see the findings.
