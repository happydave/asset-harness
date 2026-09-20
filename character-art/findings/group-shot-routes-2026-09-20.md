# Findings: which group-shot route survives contact

**Date:** 2026-09-20
**Track:** character-art
**Verdict:** partial — one route adopted, one kept as a scoped fallback, two rejected

Evidence for [WI 1626](../../../tickets/docs/pending/1626-ah-spike-group-shot-route/spike.md), which
holds the design, the falsifiable checks and the verdict. This file is the artifact record: what was
run, what came out, and which image shows it.

## Goal

Group shots are the `character-art` track's fourth deliverable and the one `design-character-art.md`
could not route. It named three candidate routes and adopted none, because the choice needed a
measurement.

The difficulty is two measured facts, not an impression: the Danbooru vocabulary cannot express
spatial layout at all (WI 1591 round 2), and every consistency mechanism the track has operates on
one character at a time.

## Tooling

- **Checkpoint:** `ilustmix_v9.safetensors` — the house style (design D7) — for every route
- **ControlNet:** `xinsir/controlnet-union-sdxl-1.0` promax, **Apache-2.0**, 2.51 GB, downloaded for
  route 3; `SetUnionControlNetType` type `openpose`
- **Upscaler:** `RealESRGAN_x4plus_anime_6B`, every route scored at 2688×1536
- **Cast:** WI 1599's four frozen subjects, via WI 1611's masters and mattes
- **Nodes:** ComfyUI 0.34.6 core throughout. Route 4 needs `ConditioningSetAreaPercentage` +
  `ConditioningCombine`; nothing custom
- **Held constant across routes:** prompts per route role, seeds 5101/5102/5103, dpmpp_2m/karras,
  30 steps, CFG 5.0, CLIP skip −2, 1344×768 generation
- **Host:** `ai2`, R9700/gfx1201, ephemeral rootless-podman container on loopback 7126, reusing
  WI 1611's image unchanged
- **Code:** `../prototypes/group-shot/`

## Licensing

| Artifact | License | Commercial? | Redistribute? | Source |
|---|---|---|---|---|
| `ilustmix_v9` | third-party merge, unestablished | no | no | design D2 — personal lane only |
| `controlnet-union-sdxl-1.0` promax | Apache-2.0 | yes | yes | `xinsir/controlnet-union-sdxl-1.0` |
| `RealESRGAN_x4plus_anime_6B` | BSD-3-Clause | yes | yes | xinntao/Real-ESRGAN |

- **Effective output license:** personal lane only, on the checkpoint. Unchanged by this spike.
- The ControlNet is a **tool rather than a style** and its Apache-2.0 licence adds no constraint —
  worth stating because design D2's "personal-lane only" rule is about checkpoints and someone will
  eventually ask whether it swept this in too.

## The four routes

| # | Route | Layout comes from | Identity comes from |
|---|---|---|---|
| 1 | Direct generation | nothing | the prompt |
| 2 | Composite | a paste coordinate | the master's own pixels |
| 3 | Pose-template control | a drawn OpenPose scaffold | pasted masters, then low-denoise inpaint |
| 4 | **Regional conditioning** | `ConditioningSetAreaPercentage` | per-region prompts |

Route 4 is not in the design. It was added because the design's "booru cannot express layout"
premise constrains the **prompt** and not the **graph** — the argument is in the spike's Design.

## Results

### Axis A — identity, scored from head bands at native resolution

The judgement is made from a full-resolution crop of the top 42 % of the frame, never from the whole
image. That is not fastidiousness: WI 1599's contact sheet nearly selected the worst half-orc in its
set because that figure stood further back and its tusks had the fewest pixels.

| Route | Result |
|---|---|
| 1 | **The cast is not present.** Across 3 seeds: no dragonborn snout in any; 5–6 figures instead of 4; tails and horns distributed onto whichever body the sampler chose. See `route1-band-right.png` — two green horned figures, neither of them anyone's character |
| 2 | **12/12 features, both denoise levels.** Tusks, red skin, horns, spade tail, snout, scale texture all intact — they are the master's own pixels. `route2-band-left.png`, `route2-band-right.png` |
| 3 | 12/12 present, **but features are added**: the half-orc acquires a horn pair he does not have and the tiefling a second one, from the discarded posed figures showing past the inpaint mask. `route3-final-band-left-artifacts.png` |
| 4 | **~26.5/36 across 3 seeds.** Structural features survive; two subtle ones do not |

Route 4's misses are specific and consistent, not random:

| Feature | Kind | Route 4, 3 seeds |
|---|---|---|
| dragonborn snout, scale texture, no human nose | structural | intact |
| tiefling horn pair, spade tail | structural | intact |
| half-orc jaw mass, green skin; human beard | structural | intact |
| **half-orc tusk pair** | small, discrete | absent 3/3 (faint on 5102) |
| **tiefling red skin** | colour | absent 3/3 (tan) |

**Those two misses are the checkpoint's, not the route's.** WI 1617 measured IlustMix as worse than
WAI at exactly half-orc tusks while beating it everywhere else, and WI 1616 found the discreteness
rule has a size floor. Route 4 regenerates from tags, so it inherits the checkpoint's weaknesses;
route 2 carries pixels, so it does not. This is the clearest evidence yet for
[WI 1630](../../../tickets/docs/pending/1630-ah-character-lane-checkpoint-search/workitem.md)'s
premise that race-feature legibility is a distinct axis from general quality.

### Axis B — layout control

Target order **half-orc, tiefling, human, dragonborn** — deliberately not the roster order, so a
route that reproduces an enumeration cannot be mistaken for a route that was controlled.

| Route | Order hit | Foreground figure count |
|---|---|---|
| 1 | no relation to target | 5–6 |
| 2 | exact, by construction | 4/4 |
| 3 | exact, all four at target position and relative height | 4/4 |
| 4 | correct in 3/3 seeds | 4/4 on one seed, 3/4 on the other two |

Route 4's failure mode is a region that yields a background figure rather than a foreground one —
the human on seed 5102, the dragonborn partly on 5103. Workable against a candidate-and-pick driver,
which is how this estate already runs the music-video stages, but it is a real 1-in-3 full-success
rate and is not hidden here.

### Axis C — scene integration

Added to the work item's two axes because those two hand route 2 the win by construction: it scores
perfectly on both and fails on neither, while the thing it actually risks — reading as four cut-outs
rather than one scene — goes unmeasured.

| Route | Reading |
|---|---|
| 1 | **best** — depth, occlusion, figures at varied distance, background patrons, one light |
| 4 | **very good** — one pass, figures at varied depth, consistent lantern light, one room |
| 3 | fair — coherent plate, but pasted figures plus visible residue |
| 2 | **weakest** — even spacing, no overlap, no occlusion, no cast shadow; reads as a lineup |

One property of the four was measured rather than judged. **Warmth** (mean R−B) of each figure's
torso against the plate above the heads, on identical boxes and identical subjects, with only the
unify pass varying:

| Route 2 stage | mean abs figure-to-plate warmth gap |
|---|---|
| raw composite | 17.84 |
| unified, denoise 0.20 | 19.27 |
| unified, denoise 0.25 | 19.22 |

**The unify pass does not integrate the figures' colour with the plate.** The gap does not shrink;
it grows slightly. The design's argument for route 2 rests on "one low-denoise finishing pass to
unify lighting", and on this scene that pass bought essentially nothing — compare
`route2-composite-raw.png` with `route2-unified-d020.png` and the difference is a small global
contrast shift.

**The instrument's limit, stated because the number invites over-reading:** warmth is confounded by
subject albedo, so it cannot compare a red tiefling against a green half-orc, or one route against
another. It is valid only for the before/after above, where content is fixed and the pass is the
only variable.

## Controls

| Check | What it would have shown | Result |
|---|---|---|
| **FC1, route 4** — regions collapsed to full frame, same seed | layout was the seed's, not the mechanism's | **passed** — one blended chimera, not four figures (`route4-FC1-control-regions-collapsed.png`) |
| **FC1, route 3** — ControlNet strength 0, scaffold still loaded | ditto | **passed** — collapses exactly onto route 1's seed-5101 image (`route3-FC1-control-strength-0.png`) |
| **FC2** — target order ≠ roster order | a route echoing an enumeration | **passed** — routes 2/3/4 hit the target order, which no file the model sees contains |
| **FC3** — same scorer applied to route 1 | the scorer cannot detect identity loss | **passed** — route 1 scores a clear failure |
| **FC4** — head crops at native resolution, never contact sheets | small features lost to sheet scale | **applied throughout** |

Route 3's control is the strongest single result here: at strength 0 it reproduces route 1's image
exactly, so the entire difference between the two is attributable to the scaffold.

## What this did not cover

Four humanoid bipeds of similar height standing in a row is the easy case. Untested: a mounted
figure, a prone one, a size disparity such as halfling beside goliath, and **physical contact
between figures** — which is the case route 2 structurally cannot do, since it pastes
non-overlapping cut-outs.

**Ground contact went untested by accident**, and that is a flaw in this spike rather than a
limitation of the routes. The knee-up framing was chosen to buy pixels for the identity axis; it
also crops out the floor where the figures' feet would be, removing one of the four properties
axis C was defined on. A follow-up wanting axis C in full needs a full-body framing and a bigger
canvas.
