# music-video: the vocal/lyrics license lane

**This lane is clean by process, not by construction.**

Every other track in this repo records a *static* license verdict: the weights are MIT or Apache-2.0,
the provenance is documented, and that settles it for everything the track produces. This track cannot
work that way. Whether a given output is clean depends on **what the lyrics say and what the prompts
name** — not on which model produced it. Two songs from the same MIT-licensed model, same seed range,
same box, can land on opposite sides of the line.

So this document does not grant a clearance. It names the exposures, says which are real and which are
noise, and binds each one to the pipeline gate that checks it.

> **Not legal advice.** This is an operating policy for a hobby/indie asset pipeline, written from the
> research in [WI 989](../../../tickets/docs/pending/989-ah-music-video-track/discover.md) and the
> owner's direction of 2026-07-21. It exists to make the exposures explicit and give each one a
> control. It is not an assurance that any particular output is lawful anywhere.

## The rule

**Vocal music is permitted for standalone media artifacts** — lobby videos, promos, trailers.

**Vocal music remains prohibited as a shipped in-game audio asset.** There, the `audio` track's
standing rule continues to govern unchanged:

> *Instrumental/ambient only for shipped assets (vocal style-mimicry exposure).*
> — [`audio/README.md`](../audio/README.md)

This lane is a **bounded exception to that rule, not a repeal of it.** If you are producing a music bed
that plays inside the game, you are in the `audio` track and the answer is still no.

An **instrumental** music video needs no exception at all — it is covered by the existing audio rule
as-is. This document is only about vocals.

### Distribution matters more than generation

The two intended uses are not equivalent, and the difference is not the pipeline — it is where the
output ends up.

| Use | Where it lands | Stakes |
|---|---|---|
| Clamor lobby video | **distributed inside a shipped product** (embedded in the server binary via `go:embed`) | higher — it travels with the game to every player |
| Promo test run | may never be published at all | lower — an unpublished artifact exposes nothing |

Generating a thing is not the risk event. **Shipping it is.** A promo cut that stays on the workstation
and a lobby loop that goes out with every build deserve different levels of care at the gates, and the
findings entry should record which one an output was made for.

## The exposures

Six distinct things get bundled together as "AI music is risky". They are not the same, they do not
share a body of law, and they do not share a mitigation. Ranked by how much they should actually
occupy you:

### 1. Lyric text — copyright — **the one that matters most**

If generated lyrics reproduce or closely track the lyrics of an existing song, that is ordinary text
copyright infringement. Nothing about the model's license touches this: MIT weights do not launder
infringing output any more than a text editor's license would.

This is simultaneously **the most concrete exposure and the most controllable one**, which is why it
sits at the top. Lyrics are short, readable, and checkable before a single second of audio is rendered.

- **Control:** prompt hygiene (below) + an originality check on the lyric sheet.
- **Gate:** the **lyrics gate** — before any song is generated.

### 2. Vocal timbre / performance likeness — right of publicity — **not copyright**

A generated voice that resembles an identifiable performer is a **likeness** problem, not a copyright
one. Different body of law, and one that varies sharply by jurisdiction. Copyright analysis will not
tell you anything useful about it.

Do not conflate this with #1. They are checked at different times, by different means: you read lyrics,
you *listen* for a voice.

- **Control:** no artist names in the style tags; reject a candidate that reads as a specific,
  identifiable singer rather than as a genre.
- **Gate:** the **candidate-pick gate** — while listening to the 3–5 candidates.

### 3. Melodic / compositional similarity — copyright

The tune resembling an existing composition. Real, and much harder to police than lyrics — you cannot
grep a melody, and unconscious similarity is a live question even for human songwriters.

Largely mitigated by not steering at a specific song in the first place. If you never ask for
"something like *<title>*", the odds of landing on it are the ordinary background rate.

- **Control:** don't prompt toward a named song; if a candidate sounds familiar, treat that as
  evidence and drop it.
- **Gate:** the **candidate-pick gate**.

### 4. Image and video prompts — copyright + trademark

Naming franchises, characters, or living artists in the Z-Image or Wan2.2 prompts. This is the same
class of problem the other visual tracks already have, but it is **sharper here** because a music video
is public-facing in a way that a texture atlas is not.

- **Control:** prompt hygiene (below), applied to shot prompts as well as to lyrics.
- **Gate:** the **shot-list gate** — the manifest is reviewable prose, so the prompts are readable
  before anything renders.

### 5. Training-data provenance — unchanged, and not specific to vocals

ACE-Step 1.5's claim to be "trained entirely on royalty-free non-copyrighted material" is a **vendor
claim** — recorded at **Supported**, not Confirmed, because it has not been independently audited.

This is worth stating precisely because it is *not new*: it applies identically to the instrumental
beds this repo already ships. Adding vocals does not change it. It is the background condition of the
whole audio track, not a reason to treat this lane differently.

### 6. Model weights license — **clean, and not the issue**

ACE-Step 1.5 is **MIT** (Confirmed, from the repo's `LICENSE` file). Z-Image is Apache-2.0. Wan2.2 is
Apache-2.0. Demucs is MIT, WhisperX BSD-2-Clause.

This is listed last deliberately. It is the cleanest fact in the chain and therefore **the one most
likely to be mistaken for a general clearance** — "the model is MIT, so we're fine" is precisely the
reasoning this document exists to prevent. A permissive weights license says nothing about exposures
1–4.

## Prompt hygiene

Concrete rules, applicable at every gate:

- **Never paste existing lyrics** into the lyrics field — not as a seed, not as a structural example,
  not "just to get the meter right".
- **Never write "in the style of `<artist>`"**, in tags or in prompts. Describe the *sound* instead:
  genre, instrumentation, tempo, mood, vocal register.
- **Never name a living artist, band, franchise, or trademarked character** in an image or video
  prompt. Describe the subject.
- **Never steer at a specific song**, by title or by "sounds like".
- Prefer describing **what you want** over **what it should resemble**. This is also better prompting.

If a prompt would embarrass you if it appeared verbatim in a credits roll, it fails.

## What a findings entry must record

Every `music-video` findings entry uses the standard [`_template/findings.md`](../_template/findings.md)
licensing table — per-artifact rows and an **effective output license** line, same as every other
track. On top of that, this track requires:

- **Vocal flag** — does this output contain sung lyrics? (If no, this lane does not apply; the `audio`
  rule does.)
- **Intended use** — standalone media artifact, and if so which: unpublished test, or shipped-with-product.
- **Lyric provenance** — that the lyrics were model/LLM-authored for this project, and that no existing
  lyrics were used as input.
- **Checks performed**, each with an outcome and the gate it ran at:

  | Check | Gate | Outcome |
  |---|---|---|
  | Lyric originality | lyrics | pass / concerns / n/a |
  | Voice likeness | candidate-pick | pass / concerns / n/a |
  | Melodic familiarity | candidate-pick | pass / concerns / n/a |
  | Prompt hygiene (shots) | shot-list | pass / concerns / n/a |

A findings entry that records "MIT weights" and stops has not documented this track's actual risk
surface.

## Gate names are forward references

"Lyrics gate", "candidate-pick gate" and "shot-list gate" name a pipeline that does not exist yet —
[WI 1004](../../../tickets/docs/pending/1004-ah-music-video-walking-skeleton/workitem.md) builds the
first version of it, and the full gated pipeline comes after.

This is deliberate and the dependency runs in this direction on purpose: **a check with no gate is not
a control.** Naming the gate here is what makes each control real, and it tells the pipeline what it
has to provide. When the pipeline lands, reconcile the names — do not quietly drop a check because the
gate it names was built under a different one.
