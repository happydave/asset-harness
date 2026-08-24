# The Lantern Fleet — lyrics (2026-07-26)

Two original songs set in [the Lantern Fleet](lore.md). Written against the
[lyric-refinement checklist](../clamor-night/lyrics.md): concrete nouns, even meter, one repeatable hook,
open vowels on the held notes, near-rhyme over forced rhyme, load-bearing `[verse]/[chorus]/[bridge]`
tags. Song A shown draft→critique→revise so the method is legible; Song B lands already-refined.

The pair takes the two halves of a Lamplighter's life: the **first crossing** (joy, before the cost) and
the **mercy cut** (the cost, carried for good) — the same two-POV structure as Clamor's
Quiet-Mile/Count-the-Faces and Archie's Dead/Hum.

---

## Song A — "Lamplighter" (Wren's first crossing)

POV: Wren, on her first solo run across the Duskreach. Buoyant, brave, a little scared. The joy the job
is *for*, before she learns the other half.

### v1 (draft)
```
[verse]
First run out and the sky is wide
A little flame pinned to my side
Three dark Beacons on my list
And a whole lot of nothing I could miss

[chorus]
I carry the light, I carry the light
Across the gulf in the falling night
```

### critique (against the checklist)
- "a whole lot of nothing I could miss" (1,3) — abstract filler, no image, weak beats.
- "the falling night" — *wrong lore*: the Duskreach is perpetual dusk, never night. Costs a concrete
  world-word (the **amber hour**) and a rhyme.
- Hook "carry the light" (4,6) is good — `-ight` opens the mouth, sustains clean; keep it.
- Nothing yet from the world's own nouns (striker, keel, skiff, Beacon) — the lore is doing no work.

### v2 (refined — the take we sing)
```
[verse]
Striker at my collar, sail hauled tight
Three dim Beacons and a strip of light
The whole silver gulf going under my keel
And a fear in my teeth I can taste, I can feel

[chorus]
I carry the light, I carry the light
Prow to the dark and the wick burning bright
Hand me a Beacon and I'll bring it to flame
Light to light, I ride the amber hour home

[verse]
First one catches and the far shore lifts
Rises off the dark like a breath, like a gift
I never felt so wide awake, so free
Every light I lift, a little lifts me

[chorus]
I carry the light, I carry the light
Prow to the dark and the wick burning bright
Hand me a Beacon and I'll bring it to flame
Light to light, I ride the amber hour home

[bridge]
They'll teach me the cut when I'm older and cold
The rope you let go and the name that you hold
But tonight there's just the gulf and the glow
And a girl and a flame and the whole sky to go
```
Gains: every line now has a concrete image (striker, keel, the far shore lifting like a breath);
"Every light I lift, a little lifts me" is the whole joy of the craft in one singable line; the bridge
plants the cost that Song B pays off; near-rhyme tight/light/bright and cold/hold/glow/go carries without
bending a word.

**ACE tags:** `warm anthemic folk-rock, bright and hopeful, soaring female vocal, driving strummed
acoustic guitar, stomping percussion, swelling uplifting strings, cinematic adventure, major key,
soaring, open air` — **104 bpm, D major, 75 s.**

---

## Song B — "The Island That Went Dark" (the mercy cut at Emberfall)

POV: Wren, older. The hardest half of the craft — cutting a doomed island loose so it doesn't take its
neighbours down. The name she carries for good. Already refined against the checklist.

```
[verse]
Emberfall had the reddest lights
Tea on the ropes and warm all night
The port that everybody loved to make
And a Moth came down for the brightest sake

[chorus]
So I cut the bridges, one by one
Slow and even till the last was done
They stood at the rails and they watched me choose
And the island that went dark was the one I'd lose

[verse]
You learn the arithmetic cold and young
Two fall with it if the ropes are strung
One light spent is three lights kept
So I made the cut, and I never wept

[chorus]
So I cut the bridges, one by one
Slow and even till the last was done
They stood at the rails and they watched me choose
And the island that went dark was the one I'd lose

[bridge]
I carry Emberfall like a striker at my chest
A flame I'll never set down, and I'll never confess
Ask me how many I've saved and I'll give you the sum
And I'll leave out the one. I'll leave out the one.
```
The bridge reuses the device that recurs across these sessions (the keeper who reports the saved total
and privately withholds the one lost — Count-the-Faces' "I'll tell you four", Archie's tally). The last
line's flat repeat is the held name that won't resolve. Chorus hook `one by one` is even-metered and the
open `-un/-one` sustains.

**ACE tags:** `melancholic cinematic folk ballad, weathered warm female vocal, fingerpicked acoustic
guitar, sparse piano, low mournful cello, aching, patient, spacious, minor key, elegiac` — **68 bpm,
A minor, 75 s.**

---

## Plan for generation

Both at **turbo** (the default) with the **−1 dBTP save-time ceiling** and the truncation guard, a seed
sweep each, best-of picked by Audiobox CE (the scorer that tracks owner taste). Watching every ACE job's
GPU for the 3 %-activity stall (restart ComfyUI if it appears — not `setperflevel`, per the corrected
archie-night diagnosis).
