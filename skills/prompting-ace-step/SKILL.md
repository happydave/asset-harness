---
name: prompting-ace-step
description: Use when writing tags/lyrics or setting duration/steps for an ACE-Step 1.5 song with sung vocals in ComfyUI — the music-video track's songs.
---

# Prompting ACE-Step 1.5

## Overview

ACE-Step 1.5 generates a full track **with sung lyrics** from two independent inputs: a **tags/style**
string (the sound) and a **lyrics** block (the words). They do different jobs — write each deliberately.

## Recipe

| Setting | Value |
|---|---|
| Checkpoint | **`turbo`** (default): 8 steps / cfg 1.0. `base` (40 / 5.0) is for comparison only |
| Sampler | euler / simple, ModelSamplingAuraFlow shift 3 |
| Encoder params | `cfg_scale 2.0, temperature 0.85, top_p 0.9, top_k 0, min_p 0.0` |
| Fields | `bpm`, `duration` (s), `timesignature 4`, `language`, `keyscale` |
| Negative | `ConditioningZeroOut(positive)` |
| Save | −1 dBTP ceiling (pure gain); a truncation warning = the song ran out of time |
| Candidates | several seeds (`--seeds 701,702,703`) → pick the best, then lock that seed |

## Writing the tags

Comma-separated descriptors, ordered **genre → instruments → mood → vocal character → BPM** (genre first
anchors the rest). Name **specific instruments** and the **vocal character** you want (e.g. "gritty clean
male vocal") — this steers the voice without naming a singer. A handful of tags, not a wall. Avoid
contradictory tags (`aggressive, serene`). Keep tag-mood aligned with lyric-mood.

## Writing the lyrics

- **Author them original** — never paste existing lyrics.
- Use section tags: `[verse]` / `[chorus]` / `[bridge]` / `[intro]` / `[outro]`. They shape the
  arrangement **and** join a lyric line to a shot. Add a modifier to steer delivery: `[chorus - anthemic]`.
- Keep lines **singable: ~4–8 words / 6–10 syllables**; the model sings ~2–3 words/sec, so match word
  count to duration. **Repeat the chorus verbatim** for a consistent hook.
- Ad-libs / backing vocals go in **(parentheses)**; **UPPERCASE** = emphasis. For an instrumental
  passage use a bare `[inst]` marker *or* empty lyrics + an `instrumental` tag — not both.

## Vocals & licence (the sharp edge)

Vocals are for **standalone media only** (lobby video, promo), **never a shipped in-game audio asset**.
No artist names in tags; never steer at a named song. Record the lyric-originality / voice-likeness /
melodic-familiarity checks in the findings entry.

## Common mistakes

| Mistake | Correct approach |
|---|---|
| Pasting real lyrics as a meter guide | Author original always |
| "in the style of \<artist\>" | Describe genre/instrumentation/vocal character |
| One generation, take it or leave it | Several seeds → pick → lock the winning seed |
| Shipping vocal audio in-game | Standalone media only |
| Structure tags as decoration | They shape arrangement and join lyrics to shots |
| Cramming long lyric lines | 4–8 words / 6–10 syllables; match words to duration |

## Explicit AI freedom

Choose the genre/instrumentation/mood palette, original lyric content, bpm/key/duration/structure, and
seed count — no need to ask.

## Community notes (reported, not fact)

Step/CFG numbers online conflict because they're **per-variant**: Turbo fixes steps=8/cfg=1 (our
default); Base sweet-spots ~27–40. Universally echoed: batch candidates, lock the winning seed.

## Source

Recipe and structure: `../../music-video/prototypes/generate_song.py` and the WI 989 track discovery.
Licence lane: `../../music-video/license-lane.md`.
