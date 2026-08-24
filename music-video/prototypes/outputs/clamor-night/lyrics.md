# Clamor lyrics — refinement pass (night session, 2026-07-25)

Exploring the owner's ask: *"lyric rerolls / improvements... a few rounds of refinement against the
lyrics up front."* Rather than reroll the **audio** (expensive, and the seed lottery doesn't fix a weak
line), refine the **text** first — it's free, it's the one input the model can't improve for us, and a
better lyric lifts every seed.

## A reusable lyric-refinement checklist (for ACE-Step sung output)

Derived from what the model actually rewards + the track's own constraints:

1. **Concrete nouns beat abstractions.** ACE-Step renders "a dropped can" harder and clearer than "the
   danger." Concrete images also give the *video* something to show.
2. **Even meter within a section.** Keep syllable counts close line-to-line so the model finds one
   melody instead of wandering. Wildly uneven lines sing badly.
3. **Strong beats on strong syllables.** Read it aloud; if the natural stress fights a bar line, rewrite.
4. **A hook — one repeatable spine line.** It anchors the chorus, the listener, *and* the WI 1001
   alignment (the repeated chorus is the 0.04 s self-consistency check).
5. **Load-bearing structure tags.** `[verse]/[chorus]/[bridge]` are the join key from a lyric line to a
   shot in the manifest; a clear, repeated chorus gives the video its backbone.
6. **Open vowels on the held notes.** Line-ending words that open the mouth (-ile, -ay, -old) sustain
   cleanly; consonant clusters at line ends slur.
7. **Near-rhyme over forced rhyme.** Assonance ("dark / mark / pharmacy") sings truer than a hard rhyme
   that bent the word choice.
8. **No meta/announcer words.** Nothing that makes the model "narrate a title" (also the licence-lane
   no-title-card rule).

The technique below: **draft → critique against the checklist → revise.** One visible pass on song A so
the method is legible; song B lands already-refined.

---

## Song A — "The Quiet Mile" (a Scout; Silent Move)

### v1 (draft)
```
[verse]
I go first where the streets are dark
Heel to toe so I make no mark
The dead are standing but they don't see
Everyone follow close behind me

[chorus]
It's a quiet mile, a quiet mile
Nobody make a sound for a while
```

### critique (against the checklist)
- "make no mark" (1) vague; "Everyone follow close behind me" (3) is prosaic *instruction*, not image.
- Chorus (4) hook is fine ("quiet mile") but line 2 is generic filler.
- No concrete image anywhere (1) — the pharmacy, the eleven, the coats-on-hooks from the lore are doing
  nothing yet.
- Meter (2) roughly even, good — keep the 8-ish-syllable line.

### v2 (refined — the take we sing)
```
[verse]
Heel to toe, I take the dark
Roll my weight and leave no spark
Eleven standing in the pharmacy light
Coats on hooks that don't turn right

[chorus]
I'll give you a quiet mile, a quiet mile
Match my step and hold the single file
The loud part's coming but it isn't here
The quiet part is mine to steer

[verse]
No dropped can, no forced door
Nobody has to be a hero anymore
I count them slack in every stair
I walk you around them, I put you there

[chorus]
I'll give you a quiet mile, a quiet mile
Match my step and hold the single file
The loud part's coming but it isn't here
The quiet part is mine to steer
```
Gains: concrete (pharmacy light, coats on hooks, dropped can, forced door); the hook earns its repeat;
"the quiet part is mine to steer" is the Scout's whole creed in one singable line; near-rhyme
dark/spark/stair/there carries without forcing.

**ACE tags:** `hushed indie folk, single female vocal, close intimate mic, fingerpicked acoustic guitar,
soft brushed drums entering late, tense restrained build, minor key, breath and space, cinematic`
**96 bpm, A minor, 75 s.**

---

## Song B — "Count the Faces" (the colony's side; the gate log)

Already refined against the checklist. Different POV from "Hold the Line" — not the band in the city,
but the woman at the gate who writes the arithmetic.

```
[verse]
I keep the book beside the gate
I write the number when they go
I don't ask what they saw out there
I only count the faces in a row

[chorus]
Count the faces, count them twice
Don't look up, don't make them say
Let the larder cheer the crates
I just write the smaller number and I keep the gate

[verse]
Good weeks the columns match
Bad weeks I leave a little space
For a name I'm not going to write again
And a chair that's going to keep a place

[chorus]
Count the faces, count them twice
Don't look up, don't make them say
Let the larder cheer the crates
I just write the smaller number and I keep the gate

[bridge]
Four went out at the break of light
Ask me now and I'll tell you four
And I'll leave out how close four came
To being three, and never more
```
The chorus's long last line is deliberate — it lands like a ledger entry, a little too long for the bar,
the way the job is a little too heavy for the person. The bridge reuses the lore's exact device (four
went in, four came back, and what she leaves out).

**ACE tags:** `slow melancholic folk ballad, weathered female vocal, sparse piano and low strings,
mournful, patient, restrained, minor key, cinematic, lots of space` **72 bpm, D minor, 75 s.**

---

## Plan for generation

Both at **turbo** (the new default) with the **−1 dBTP save-time ceiling** — a seed sweep each
(candidates for a pick), scored with the corrected audio scorers + Audiobox as a *second opinion*, then
the best of each carried into a video. Watching the GPU on every ACE job for the 3 % stall.
