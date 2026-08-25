# Five music-video production sessions (2026-07-25 → 2026-08-13) — consolidated findings

**Date:** 2026-08-24 · **Track:** music-video · **Verdict:** works — the track ran in production for a
month and delivered seven published videos

This document consolidates five **production sessions** that ran after WI 1004 closed the walking
skeleton. Each session was self-contained work inside `prototypes/outputs/<session>/` — a gitignored
tree — so its findings never reached the project record even though the videos shipped. The session
notes are the primary record and are now committed alongside this summary; this document carries the
cross-session verdicts, particularly the ones that **supersede earlier committed conclusions**.

## The sessions

| Session | Date | Notes | Songs produced | Published as |
|---|---|---|---|---|
| [archie-night](../prototypes/outputs/archie-night/SESSION.md) | 07-25 | Wan fp8 thrash measured; stall diagnosis corrected | The Dead Don't Complain, The Hum | both |
| [clamor-night](../prototypes/outputs/clamor-night/SESSION.md) | 07-25 | lore bible + lyric-refinement checklist | The Quiet Mile, Count the Faces | both |
| [clamor-motion](../prototypes/outputs/clamor-motion/SESSION.md) | 07-27, corrected 07-28 | **the working Wan recipe**; single-stage abandoned | Told the City, Grit | neither |
| [lantern-fleet](../prototypes/outputs/lantern-fleet/SESSION.md) | 07-26 | own universe; model-eviction slowdown found | Lamplighter, The Island That Went Dark | Lamplighter only |
| [lantern-crossing](../prototypes/outputs/lantern-crossing/SESSION.md) | 07-29, resolved 08-13 | **clip chaining** proven; ai2 GPU blocker | Between the Lights | yes |

Seven videos are live at `scienceranch.com/videos/` (WI 1103): the six above plus **Hold the Line**, the
WI 1004 lobby cut. The three unpublished songs were produced but not selected for the site; the two
clamor-motion cuts are also the only two that carry Wan motion clips.

## Wan2.2 i2v — the recipe that produced the delivered clips

**This supersedes the recipe in `skills/prompting-wan-i2v/SKILL.md` as written at the time**, which was
distilled from WI 1018/1019 before any motion clip had been cut for delivery.

> **UPDATED 2026-08-25** ([WI 1161](2026-08-25-wan-fp8-vs-fp16-and-the-mmap-flag.md)): delivery has since
> moved to **fp8** under this same 2/2 split — 3.0× faster (127 s vs 384 s), no lowvram spill, half the
> host RAM, at the cost of a marginal softness. The `~6–10 min/clip` below was fp16 *and* depended on
> `--disable-mmap` being on, which it was in July and was not between 08-05 and 08-25. Everything else
> in this section stands.

The working configuration is ai2's saved workflow at
`/opt/comfyui/user/default/workflows/wan2.2-test.json`, replicated by `generate_clip.py --fp16` — the
two-stage MoE run properly:

| Setting | Value |
|---|---|
| Stages | **both experts** — high-noise runs sampler steps 0→2, hands the latent to low-noise for 2→4 (`return_with_leftover_noise` on stage 1, `add_noise=disable` on stage 2) |
| Checkpoints | **fp16** (`wan2.2_i2v_high/low_noise_14B_fp16`), *not* fp8_scaled |
| LoRA | **both `lightx2v_4steps` LoRAs**, one per stage |
| Steps / cfg | 4 / **1** |
| Sampler / scheduler / shift | euler / simple / ModelSamplingSD3 **5** |
| Resolution / frames | 1280×720, 33 f @ 16 fps (≈2.06 s) |
| Cost | **~6–10 min/clip** — fp16 loads dominate (28 GB read per stage, per clip) |

**Why the earlier "two-stage is impractical" reading was wrong.** archie-night measured a 5 s fp8 clip
spending ~99% of wall-clock swapping the two 14 GB checkpoints — ~10 s of compute inside 17+ min — and
concluded the two-stage MoE could not fit. That was the **fp8 both-resident** path. Splitting the
schedule 2/2 means only **one model is resident at a time**: high loads, does its two steps, and the run
swaps **once** to low — not once per sampling step. VRAM peaks ~33.5 of 34 GB, tight but not OOM.

**Why single-stage was abandoned.** archie-night's proposed fix — one expert over the whole schedule, no
swap — was built as `generate_clip_single.py` and is fast, but off-distribution: low-noise alone wanders
(night→day, anime-style pop-ins, scene morph) and high-noise alone softens and barely moves. Wan2.2
needs both experts. The file is kept as a record of the experiment with a header saying so.

**On the "LoRA kills motion" rule.** WI 1018/1019 found the 4-step lightx2v LoRA produced near-static or
swirling output and recommended `--no-lora` at 20 steps. The production recipe uses **both LoRAs and 4
steps** and yields clean coherent motion. These are consistent: the LoRA is part of a 4-step schedule
split across two experts, and fails when bolted onto a configuration it was not trained for. Prefer the
`wan2.2-test` recipe as a whole rather than mixing settings between the two.

**Prompting.** clamor-motion reports that **scene-description prompts with gentle motion verbs**
("zombies slowly stumbling") work, and that camera-move language drove drift. The evidence for the
camera-language claim comes from the single-stage runs, so treat it as a reported preference for the
two-stage path rather than a tested result there.

**Speed idea, since tested (WI 1161):** two-stage with **fp8** under the same 2/2 split is **3.0×
faster** (127 s vs 384 s) and is now the delivered recipe — but *not* for the reason proposed here. Both
stages do **not** stay resident: ComfyUI evicts between stages at either dtype. fp8 wins because it fits
without spilling, where fp16 offloads ~1.8 GB and runs 33–36 lowvram patches. See
[the spike findings](2026-08-25-wan-fp8-vs-fp16-and-the-mmap-flag.md).

## Clip chaining — continuous shots longer than one clip

lantern-crossing proved that two 6 s clips can read as one continuous 12 s shot:

1. Generate clip 1 (97 f @ 16 fps) at **832×480** — 6 s at 720p OOMs (97-frame latents push VRAM to
   33.3 GB even at 480p).
2. Extract its last frame and clean it with a **content-preserving** ffmpeg pass: `hqdn3d` light denoise
   + moderate `unsharp` luma + a touch of contrast/saturation. This sharpens **without moving content**,
   which is what preserves the seam.
3. Generate clip 2 from the cleaned frame, prompt continuing the motion.
4. Concat. Because i2v reproduces its start frame at frame 0, clip 2's frame 0 ≈ cleaned(clip 1 last),
   so the seam is content-continuous with no positional jump — a faint acuity lift and i2v's slight
   motion restart are the only artifacts, and a short crossfade hides both.

Verified on a 12 s skiff flight (scene-scores ~0.005–0.014 across the seam), used as the spine of
*Between the Lights*. **A low-denoise img2img cleanup would restore more detail but shifts content and
breaks the seam** — the ffmpeg pass is the right tool for continuity. No upscale model (RealESRGAN or
similar) is installed on ai2. Filed as a work item to productize.

## ai2 ComfyUI — two distinct slowdowns, different fixes

Three sessions hit performance problems that look alike from the outside and are not the same thing.

| Symptom | GPU trace | Cause | Fix |
|---|---|---|---|
| **Load hang** | stuck ~3% activity, ~50 MHz, idle power; job never finishes | silent hang mid model-load (log shows `got prompt` → `VAE load device…` → nothing) | `systemctl restart comfyui.service` — the **only** cure |
| **Evict-every-job** | ramps to ~100% normally, but every job re-reads its full model set (~19 GB) from disk | a prior lowvram/partial job (Wan) leaves the model manager in a conservative offload-everything state, even at 14.5/34 GB used | restart clears it; models then stay resident (~6× faster) |

Healthy fingerprint, from a 22-job trace: idle 3% / ~42 MHz / 23 W; compute ~100% / 1885–3464 MHz /
304–344 W. Every healthy job ramps the instant compute starts, so **3% activity during a "running" job
is the unambiguous tell** for the load hang.

**A superseded hypothesis, recorded because it was tested.** clamor-night proposed the stall was a DPM
clock lock fixable with `setperflevel high`. archie-night caught the stall live and **refuted it**:
forcing the perf level raised power (24→54 W) but activity stayed at 3% and the clock at ~57 MHz,
because the job is not issuing GPU work for a clock to ramp for. `/interrupt` does not clear it either
(it only interrupts sampling, which is never reached). This also explains the WI 1043 "500 s" mystery —
that was this hang, and the reboot that "fixed" it simply cleared the wedge.

**Operational rule:** after a big Wan (or any lowvram/partial) job, restart ComfyUI before a batch of
ACE-Step or Z-Image work, or every job pays a full disk reload.

A third state appeared on 07-29 and is **not** either of the above: SCLK pinned at ~41 MHz under load,
surviving both `setperflevel high` and repeated ComfyUI restarts — a GPU power/clock state, not a
software one. It cleared on its own without a reboot (confirmed 2026-08-13).

## The song pipeline held up in production

The WI 1043 turbo default, the WI 1046 QC meter and the WI 1045 scorer fixes were all exercised on
material nobody hand-picked:

- **Turbo generation ran 12.7–15.2 s per song** across every session.
- The **−1 dBTP save-time ceiling fired routinely** — several songs came in hot at 0 to +0.1 dBTP and
  were trimmed to −1.00 automatically.
- The **truncation guard fired live** on `count_faces` seed912, which independently also scored lowest
  on Audiobox CE — and on archie's `The Dead` seed501, where it steered the pick away from the
  highest-CE candidate. The guard and the scorer corroborate each other.
- **Audiobox CE was the song selector in all five sessions** (~27 candidates across 9 songs — three seeds per song wherever the count is recorded).
  WI 1045 found it reproduced the owner's ranking exactly at n=4 and flagged the sample size; these
  sessions are the larger sample that flag was waiting for, and the picks were shipped. **This is
  direct input to the WI 1035 promotion design** — it is the strongest evidence the track has that a
  machine signal can select rather than merely gate.

## The renderer needed no changes

clamor-motion mixed stills and motion clips using a hand-authored **variable-duration beat map** (motion
clips get ~3 s windows so the settle is brief) and found `render.py` already handled it: `kind: "video"`
fits a clip to its window by scale/crop to 1280×720, holding the last frame if short and trimming if
long. The manifest→pure-renderer boundary from WI 1004 absorbed a shot kind it had never been exercised
on without an engine change.

One authoring rule came out of it: **never place a motion clip immediately before or after its own
source still** — lantern-crossing hit this and fixed it by excluding the flight's source frame from the
still set.

## Reusable material left in the session tree

The session drivers (`*_songs.py`, `*_stills.py`, `build_*_video.py`, `clamor2_clips_v2.py`,
`crossing_*.py`) remain gitignored under `prototypes/outputs/` — they are per-session drivers, not
harness code. Two artifacts are worth knowing about:

- The **lyric-refinement checklist** in [clamor-night/lyrics.md](../prototypes/outputs/clamor-night/lyrics.md),
  reused by every later session, with one song shown draft→critique→revise so the method is legible.
- Two **world bibles** — the Hold ([clamor-night/lore.md](../prototypes/outputs/clamor-night/lore.md)),
  grounded in Clamor's own vocabulary from its design docs, and the Lantern Fleet
  ([lantern-fleet/lore.md](../prototypes/outputs/lantern-fleet/lore.md)), an original setting written in
  session. Archie has no bible — those two songs were written against an owner-supplied story.

`ai2:~/gpu_trace.py` (amd-smi sampler → CSV) was left on the box by clamor-night.
