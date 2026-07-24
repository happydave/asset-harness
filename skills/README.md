# Model prompting skills

Per-model **prompting and usage guides** for the generative models this repo drives. One skill per
model, added as we validate a model in-repo. When you are about to write a prompt (or pick
steps/cfg/resolution) for a model listed below, read its skill first — it captures the wording,
settings, and traps we have already paid for.

## Skills

| Skill | Model | Drives |
|---|---|---|
| [`prompting-wan-i2v`](prompting-wan-i2v/SKILL.md) | Wan2.2 i2v-A14B (image-to-video) | `music-video/prototypes/generate_clip.py` |
| [`prompting-z-image`](prompting-z-image/SKILL.md) | Z-Image base/zanime (text-to-image) | `music-video/prototypes/generate_still.py` |
| [`prompting-ace-step`](prompting-ace-step/SKILL.md) | ACE-Step 1.5 (text-to-music, sung lyrics) | `music-video/prototypes/generate_song.py` |

## Conventions

- **Format:** follow the `writing-skills` skill (superpowers) — each skill is a directory with a
  `SKILL.md`, a hyphenated `name`, a `description` stating *triggering conditions only*, and a body that
  is **directive, not narrative** (no "we found / WI-123 proved …" — provenance goes in a one-line
  *Source* pointer to the findings) and **under ~500 words**. That doc is the format authority; this
  README is not.
- **Only skill a model we have actually driven in-repo.** A prompting guide written ahead of real usage
  is invented guidance. Evidence — a `generate_*.py` graph and a `findings/` entry — comes first, then
  the skill distills it.
- **Two layers, kept separate, in every skill:** (1) the *portable* model-prompting core (wording,
  ordering, negatives, failure→fix) that any project could reuse, and (2) *our validated setup* — the
  exact graph, defaults, and hardware-specific recipe (asset-harness on `ai2`), clearly labelled as ours.
- **Community-reported ≠ fact.** Web-sourced guidance is attributed and framed as reported success; our
  own validated evidence governs our recipe. Where they diverge, both are shown.
- **Prompt hygiene is a hard gate.** Image/video/lyric prompts obey
  [`music-video/license-lane.md`](../music-video/license-lane.md): no franchise, character, living-artist,
  or named-song references. "If it would embarrass you in a credits roll, it fails."
- **Discoverability:** the global skill convention points at `tickets/skills` + `superpowers/skills`, not
  this repo, so the repo `README.md` links here to make these surface when working in `asset-harness`.

## Adding a model (the shared skeleton)

Drop a new `prompting-<model>/SKILL.md` using this mold (the next one is likely **Qwen-Image-Edit** from
the realifier spike):

```markdown
---
name: prompting-<model>
description: Use when [writing a prompt / picking settings] for <model> in ComfyUI — [what it's for].
---

# Prompting <model>

## Overview
[One or two sentences: what the model is, its lineage, where it runs.]

## Inputs & what each does
[The prompt fields / image inputs and the role each plays.]

## Our validated recipe
[Exact generator, defaults, owner-confirmed numbers — labelled as ours, ai2-specific.]

## Writing the prompt
[Wording, ordering, what to describe vs omit. Positive framing.]

## Negatives
[Whether/what to use.]

## Failure → fix
[Common artifacts and the prompt-side or setting-side fix.]

## Community-reported patterns
[Attributed, framed as reported-success. Note agreement/divergence with our recipe.]

## Common Mistakes
| Mistake | Correct approach |
|---|---|

## Explicit AI Freedom
[Decisions the prompt author makes without asking.]
```
