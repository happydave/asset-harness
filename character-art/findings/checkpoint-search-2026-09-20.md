# Findings: is IlustMix the best checkpoint available for the character lane?

**Date:** 2026-09-20
**Track:** character-art
**Verdict:** works — IlustMix survives in both roles; the Pony family is eliminated for generation

Evidence for WI 1630 (`tickets/docs/pending/1630-ah-character-lane-checkpoint-search/spike.md`),
which holds the design, the controls and the verdict. This file is the artifact record.

## Goal

Design **D7** made `ilustmix_v9` the house style provisionally, on the owner's observation that the
installed checkpoints were "a few of the overall top rated models without looking for DnD tuning".
So IlustMix was the best of an arbitrary set rather than the best available. This asks whether
anything beats it on **race-feature legibility** — the axis WI 1617 showed does *not* track overall
quality.

## Tooling

- **Six installed checkpoints**, all booru-tag SDXL: `waiIllustriousSDXL_v170`, `ilustmix_v9`,
  `nova3DCGXL_illlustriousV50` (Illustrious); `prefectPonyXL_v6`, `ponyRealism_V23`,
  `cyberrealisticPony_v180Coreshift` (Pony)
- **Cast:** the four WI 1599 subjects at their own seeds, 768×1344, dpmpp_2m/karras, 30 steps,
  CFG 5.0, CLIP skip −2 — WI 1617's settings, so results are comparable to that record
- **Family-correct quality prefixes**, Pony's score chain verbatim and never negated
- **Host:** stage 1 on `ai2`'s shared `comfyui.service` (used, not modified); stage 2 in the
  WI 1626 container on loopback 7126
- **Code:** `../prototypes/checkpoint-search/`

## The candidate space is narrower than it looks

The lane is **booru-tag** (design generation lane 1): the roster's `tags` column is booru,
`CLIPSetLastLayer -2` is mandatory, and the vocabulary procedure is a Danbooru post-count lookup.
DreamShaper, Juggernaut, RealVis and the rest of what a "best fantasy SDXL" search returns are
natural-language models — adopting one would not be a better checkpoint for this lane, it would be
a different lane, and it would strand the roster. **Illustrious-family or Pony-family, and nothing
else.**

## Results

### The dragonborn decides it

| Checkpoint | Dragonborn |
|---|---|
| `ilustmix`, `nova3dcg`, `wai` | proper draconic head — long snout, scales, frills, reptilian eyes |
| `prefectpony`, `ponyrealism`, `cyberpony` | **complete failure** — a human or elf with horns, no snout |
| any Pony **+ `source_furry`** | unchanged. Still a horned human |

`heads_dragonborn.png`. This refutes the spike's own hypothesis, which came from WI 1591 round 2's
archive: Pony V6's `source_furry` draws on e621 data where anthro dragons live, and was predicted
to beat base Illustrious on exactly this subject.

**Stated precisely, because the distinction carries the whole weight:** none of the three installed
Pony checkpoints is base **Pony Diffusion V6 XL**. All are merges, two tuned hard toward
photorealism. What is refuted is "an installed Pony merge is better for dragonborn". The archive's
actual claim is *untested*, because the model it names is not on this box — and the archive
labelled that claim `[INFERENCE]`, not `[CONFIRMED]`.

### The other three subjects

- **Half-orc tusks** (`heads_halforc.png`) — thick and clearly protruding on `ilustmix`,
  `nova3dcg`, `wai`, `prefectpony`; small on a human-proportioned jaw on `ponyrealism` and
  `cyberpony`.
- **Tiefling** (`heads_tiefling.png`) — all nine arms pass every feature. The best-covered D&D race
  in the vocabulary, and not discriminating.
- **Human control** (`heads_human.png`) — all six produce a bearded human with no spurious
  non-human features. `cyberpony` and `ponyrealism` ignored `full body, standing` and returned
  portrait crops.

### The finishing role barely exists at the specified denoise

The WI 1611 half-orc master through img2img at denoise 0.25 on four candidates
(`stage2-finishers-and-FC2.png`):

| Finisher | mean abs difference from the master (0–255) | warmth (R−B) |
|---|---|---|
| *(master, the input)* | — | 13.79 |
| `ilustmix` | **8.03** | 15.02 |
| `nova3dcg` | 4.18 | 14.71 |
| `ponyrealism` | 4.33 | 14.85 |
| `cyberpony` | 4.40 | 15.05 |

All four preserve the tusks, consistent with WI 1611 scenario 7. And all four move the image by
4–8 parts in 255. **Swapping the finisher is not a lever for "less cartoonish"** — at 0.20–0.30 the
input dominates. This reproduces WI 1626's independent measurement of the same operation on a
different scene from the other direction.

## Controls

| Check | Result |
|---|---|
| **FC1** — reproduce WI 1617 | **failed, then passed** — see below. The most informative result here |
| **FC2** — the scorer measures tusks | **passed** — the half-orc with `tusks, protruding lower canines` removed from the prompt came out with no tusks and scored as such |
| **FC3** — the family prefix matters | **failed** — on `prefectPonyXL_v6`, the score chain, the Illustrious prefix and no prefix at all give near-identical output (`FC3-family-prefix.png`) |
| **FC4** — head crops at native resolution | applied throughout |

**FC1 is why this run is trustworthy.** Against WI 1617's committed images, `ilustmix` at seed 202
did not reproduce — different armour, pose, footwear, and *thicker tusks* where the record shows
thin ones (`FC1-failure-roster-prompts.png`). The cause is that **`roster/cast.csv` is a lossy
transcription of WI 1599's prompts**: a strict subset missing nine tags including `large jaw`, and
paired with a shorter negative. Restoring WI 1617's exact prompt and negative, FC1 passes
(`FC1-reproduction-wi1617-prompts.png`).

So the incumbent's recorded weakness is **partly a prompt-length artifact**: on the shorter roster
prompt that the live pipeline actually uses, IlustMix's tusks come out large and clear. Filed as
WI 1642 (`tickets/docs/pending/1642-ah-roster-does-not-reproduce-the-wi1599-cast/workitem.md`).

**FC3's failure strengthens the dragonborn result** rather than weakening it: the Pony merges'
failure cannot be blamed on a mis-chosen prefix, because on the one tested the prefix does almost
nothing. One checkpoint, one subject, one seed — not a claim about the family.

## What this does not cover

Four races, one seed each, one prompt set. Dwarves, halflings, goliaths and beast-folk are
untested, and the archive records the vocabulary as thin or hostile for several of them — so a
checkpoint chosen here is chosen on the easy cases. Base Pony V6 and any e621-trained NoobAI are
untested because they are not installed; **base Pony V6 is the download actually worth making**,
and it is a different question from "find a D&D-tuned checkpoint".
