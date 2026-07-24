# Wan2.2 i2v — settings tuning + interpolation (WI 1019)

**Date:** 2026-07-23 · **Box:** `ai2` (fp8) + workstation ffmpeg · **Follows**
[WI 1018 quality findings](2026-07-23-wan-i2v-quality-720p.md) (the owner's "framey/soft" note).

## Verdict: interpolation fixes the framiness; the settings bundle doesn't earn its cost

Two levers tested against the WI 1018 run #1 baseline (euler/simple, cfg 3.5, 20 steps, 16 fps):

### Interpolation — ADOPT

A **standalone workstation post-step** ([`interpolate.py`](../prototypes/interpolate.py), ffmpeg
`minterpolate` mci) raised both WI 1018 clips 16 → **48 fps** in **~41 s each** — no regeneration, no
ai2. Inspected an **interpolated** (in-between) frame on the character clip *and* the crowd clip (the
hard case): both clean, no warping/ghosting
([`samples-2026-07-23-wan-quality/interp48_*`](samples-2026-07-23-wan-quality/)). `minterpolate` is good
enough; **RIFE stays a flagged, un-installed upgrade** if temporal playback later shows artifacts on
fast motion. **This — not the settings — is what fixes the framey look**, and it's dirt cheap and
retargetable (32/48/60 fps without regenerating the ~2 h clip).

### Settings (res_multistep / sgm_uniform / cfg 5 / 30 steps) — DON'T bump

Ran the WI 1018 character still with the community-recommended bundle (else identical). Result:
**comparable to run #1, not a decisive improvement** — same push-in+walk, marginally more contrast from
cfg 5, no visible quality jump
([`samples-…/improved_char_frame*`](samples-2026-07-23-wan-quality/) vs `clip1_nolora_char_frame*`). And
it cost **+50 min** (30-step sampling ≈ 122 min vs 20-step's 72 min; `Prompt executed 02:22:47`). The
recommended settings likely help *undercooked* frames; run #1 wasn't undercooked. **Both clips are
16 fps, so settings don't touch framiness anyway.** Keep 20 steps.

The `--sampler/--scheduler/--shift` flags now exist on `generate_clip.py` (defaults unchanged) so a
specific undercooked shot *can* be tuned — but it's not the default.

## Recommended recipe for WI 1004

- **Video:** fp8, **no-LoRA, 720p, 20 steps**, euler/simple, cfg 3.5–5 (taste), shift 5.0, 81 f.
- **Then interpolate** the finished clip to **48 fps**: `interpolate.py clip.mp4 --fps 48 --out
  clip_48.mp4` (workstation, minterpolate mci).
- Interpolation triples frame count — mind the in-binary lobby-loop file budget (a 48 fps 5 s clip is
  ~3.3 MB h264 here).

## Also: a WI 1020 regression, caught by the first real clip run

The improved-settings run's client reported "no outputs to download" though the job finished. Cause:
**this ComfyUI's SaveVideo emits the mp4 under the `images` key** (`animated: True`), not `videos`, and
the WI 1020 refactor had narrowed `generate_clip`'s download to `videos/gifs`. Fixed
`generate_clip.py` + `run_batch.py` to include `images`. The clip was recovered from history
(`fetch_from_history --pid …`) with nothing lost — the WI 1020 recovery path working as designed. This
is exactly the gap WI 1020's test.md flagged (no full-clip round-trip through `run_job`); the first real
clip run found it.

## Deferred (unchanged)

Qwen-Image-Edit **realifier** (clean still artifacts) and the **per-model prompting skill** — the skill
now has its validated numbers (this recipe) to capture.
