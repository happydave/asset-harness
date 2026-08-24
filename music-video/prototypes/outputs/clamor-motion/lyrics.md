# Clamor — lyrics, motion session (2026-07-27)

Two new songs from the two **unused** [clamor-night lore](../clamor-night/lore.md) mini-stories (the
first session used the Scout and the gate-keeper; these use the Screamer and the Medic). Written against
the [refinement checklist](../clamor-night/lyrics.md). They contrast on purpose — a loud one and a quiet
one — and that split drives the **motion budget**: the loud song gets the Wan i2v clips (its chaotic
beats tolerate the single-stage model's drift, and there the drift reads as energy), the ballad stays
stills-primary and composed.

---

## Song A — "Told the City" (the Screamer; the run goes loud)

POV: the band, when a Screamer sees them and wakes the dead city. From lore mini-story #3. Driving,
tense, defiant. **This is the motion-heavy video.**

```
[verse]
Thin and grey with a lanyard still on
Stood up in the corner where the light had gone
Didn't roar, didn't charge, didn't make a sound
Just looked right at us and it passed us around

[chorus]
It told the city, told the city where we stand
Every slack shape turning down the boulevard
Now it isn't the crates, now it's only the door
Who holds it, how long, and what the Grit is for

[verse]
Fixer on the hinges that were never gonna hold
Spending all he had on a lie we'd all been told
That a door is a wall if you want it hard enough
Count the seconds, not the shells, and call the exit up

[chorus]
It told the city, told the city where we hid
One sound rising and it lifted every lid
Now it isn't the haul, now it's only the door
Four went in, and you don't get to ask what for

[bridge]
We got it shut, got the street, got the long way home
Four went in and four came out and that's the only poem
The Hold will ever write us — not the noise, not the fear
Just the count they keep at the gate, and this time everybody's here
```

**ACE tags:** `driving urgent post-punk rock, tense male vocal, pounding relentless drums, distorted
bass and guitar, dark cinematic, building dread and adrenaline, minor key` — **140 bpm, E minor, 75 s.**

---

## Song B — "Grit" (the Medic; Stabilise at range)

POV: Dell, spending his last Grit to save a man from cover at forty feet. From lore mini-story #2. Slow,
heavy, the cost of the one who makes mistakes survivable. **Stills-primary.**

```
[verse]
Okonkwo went down in the open ground
Three points left and the horde two tiles from the sound
The book says close, the book says kneel
The book has never met a street this real

[chorus]
So I spent the Grit, spent the Grit from forty feet
Watched his chest fill up while I never left my seat
You get it twice a mission, never twice in a row
I make a mistake survivable — that's the only thing I know

[verse]
I felt it leave me like a held breath goes
That warm last thing that nobody rations, nobody knows
if it's coming back, or it comes at all
I spent it on a man face-down against a wall

[chorus]
So I spent the Grit, spent the Grit from forty feet
His chest hitched and filled and I stayed down in the concrete
You get it twice a mission, never twice in a row
I make a mistake survivable — then I've got nowhere to go

[bridge]
I was empty the rest of the run and I knew it when I paid
Do it again, I'd do it again — that's the oath a Medic made
```

**ACE tags:** `slow melancholic ballad, weary soulful male vocal, sparse piano and low strings, aching,
restrained, spacious, cinematic, minor key` — **66 bpm, C minor, 75 s.**

---

## Motion plan (single-stage Wan i2v)

Single-stage i2v is affordable now (~65 s for a 3 s clip, one 14 GB checkpoint resident — see
`SESSION.md`), but it **drifts** (low-noise wanders in light/composition; high-noise softens and barely
moves). So: **stills backbone + short (~3 s) low-noise motion accents on drift-tolerant beats only.**

- **Told the City:** motion on the chaos beats — the city turning, the horde surging, the run — where
  drift *is* the energy. ~3–4 clips; stills elsewhere.
- **Grit:** one gentle motion accent (the Stabilise glow); everything else Ken-Burns stills, to keep the
  ballad still and legible.

Both songs at **turbo + −1 dBTP ceiling + truncation guard**, seed sweep, best-of by Audiobox CE.
