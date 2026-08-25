# Clip chaining productized — arbitrary-length continuous Wan shots (WI 1160)

**Date:** 2026-08-25 · **Track:** music-video · **Verdict:** works, and at full 720p

The lantern-crossing session proved two 6 s links could read as one continuous 12 s shot, but the
technique existed only as hand-run steps and its cleanup parameters were never written down. It is now
[`prototypes/chain_clip.py`](../prototypes/chain_clip.py), with the seam measured rather than eyeballed.

## Results

A 3-link chain at **1280×720**, 97 frames per link, from a single start still:

| | |
|---|---|
| Output | 291 frames = 97 × 3, 1280×720 |
| Seam 1 | SSIM 0.9579 vs local adjacent-frame norm 0.9577 — gap **−0.0002** |
| Seam 2 | SSIM 0.9510 vs local norm 0.9762 — gap **0.0252** |
| Cost | ~11 min per 6 s link |

Seam 1's gap is negative: that seam is **indistinguishable from ordinary frame-to-frame change**. Neither
seam is locatable by eye in the filmstrips.

## The seam gate

Seam quality is measured **relative to the clip's own frame-to-frame norm**, not against an absolute
threshold — because i2v reproduces its start frame only approximately (SSIM ~0.94), so a seam is
content-continuous, never pixel-continuous. Each seam must sit no more than **0.05** below the mean
adjacent-frame SSIM of the 8 frames preceding it.

Calibrated against the shipped July chain, which scores a 0.030 gap. Validated in both directions: a
deliberately hard cut between unrelated clips **fails** the gate.

## 720p works — the 832×480 ceiling was an fp16 artifact

The original technique ran at 832×480 because 97-frame latents pushed VRAM to 33.3/34 GB at fp16.
Re-probed under fp8 ([WI 1161](2026-08-25-wan-fp8-vs-fp16-and-the-mmap-flag.md)): **1280×720 × 97 f
completes with no OOM**, both stages `loaded completely`, 791 s. Chaining now runs at delivery
resolution; 832×480 remains the driver default for cheapness.

## Update 2026-08-25 (WI 1173): the sharpen compounds too, and the gate missed it

Owner review of the 3-link chain reported **over-sharpening at the 6 second mark** — the first seam.
Measured: per-frame acuity runs **1.39 → 1.74 → 2.16 → 2.4** across the three links, a **+25% step at
each seam** and **+71%** end to end. On the input side, one application of `unsharp=5:5:1.0` raises a
frame's acuity **+83.5%**; `hqdn3d` alone is +3.4%.

The sharpen was kept on the assumption that it compensated for a soft extracted frame. That is
unsupported — PNG extraction of a decoded frame is lossless, so there is nothing to restore. **It is now
off by default**, alongside the grade, leaving the cleanup close to identity.

**The seam gate passed that seam** — gap −0.0002, its best result — because SSIM is dominated by
structure and motion and barely registers a global acuity change. A second check now runs alongside it:
**acuity continuity**, requiring high-frequency energy across a seam to stay within ±10% of the local
norm. It fails the original chain on both seams (+23.1%, +26.0%) while continuity still passes them,
which is exactly the discrimination that was missing.

*Lesson worth carrying: a gate calibrated on one visible failure mode says nothing about the others. The
owner's eye caught what two automated measures agreed was fine.*

## Two things the 2-link original could not have shown

**A per-seam colour grade compounds.** The recovered cleanup ended in `eq=contrast=1.05:saturation=1.05`
and runs once per seam, so an N-link chain applies it N−1 times. A 3-link chain drifted **SATAVG 20.29 →
22.23 (+9.6%, ≈1.05²)** — while luma did *not* run away (it dips ~4 units at each seam and recovers, which
is why this had to be measured rather than eyeballed). The grade is now **off by default**; `--grade`
restores the original recipe. The sharpen, which is what actually serves the seam, is unaffected.

**The cleanup parameters were recoverable.** They were never recorded — `SESSION.md` says only "light
denoise + moderate luma + a touch of contrast/saturation" — but both ends of the pass survived as
`last_raw.png` and `last_clean.png`. Grid-searching candidates against that pair recovered the chain at
**SSIM 0.998476**:

```
hqdn3d=1.5:1.5:3:3,unsharp=5:5:1.0:5:5:0.0,eq=contrast=1.05:saturation=1.05
```

`hqdn3d` is **measurably inert** at that strength on a single frame — `unsharp+eq` alone scores
identically to six decimals, and at ffmpeg's default strength the match gets *worse*. Its temporal terms
cannot apply to one frame.

## Rules

- **Never** clean the seam frame with a low-denoise img2img or realifier. It restores more detail but
  shifts content, which breaks the seam. That also makes [WI 1162](../../../../tickets/docs/pending/1162-ah-qwen-image-edit-realifier-spike/workitem.md)'s
  realifier a stills tool, not a chaining tool.
- **Never** apply a colour grade per seam (above).
- Feed opaque RGB; the driver refuses alpha before spending GPU time.

Evidence: [`samples-2026-08-25-clip-chaining/`](samples-2026-08-25-clip-chaining/) — seam and whole-clip
filmstrips plus the run record. Full plan, review and test artifacts:
[WI 1160](../../../../tickets/docs/pending/1160-ah-music-video-clip-chaining/).
