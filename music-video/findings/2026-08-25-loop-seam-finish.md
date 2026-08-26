# Loop-seam finish — a rendered cut that survives its own end-to-start join (WI 1159)

**Date:** 2026-08-25 · **Track:** music-video · **Verdict:** works; the join is constructed, not cleaned up

WI 1004 named this its priority-1 follow-up and it sat unfiled for a month while five production
sessions shipped standalone 75 s cuts. The lobby wants the other thing: a **≤60 s cut that plays on
repeat**. It is now [`prototypes/loop_finish.py`](../prototypes/loop_finish.py), reachable from the
manifest via a `loop` block so the loop cut is a re-render, never a hand edit.

## The mechanism

Given a source cut of duration `D`, a loop length `T` and a crossfade `x` (`T + x ≤ D`):

    out[0, x)  = source[T, T+x) fading out under source[0, x) fading in
    out[x, T)  = source[x, T) unchanged

Played on repeat this runs `… src(T−δ) → src(T) …` across the join — **adjacent source material**, so
there is nothing to click on. Continuity is a property of the algebra rather than something to sand
down afterwards. One ffmpeg filter does each half (`xfade` with `offset=0`, `acrossfade` with `d=x`),
and both use the same `T` and `x`, so picture and sound stay in lockstep.

Verified frame-exactly on a grey-ramp source whose frame `N` is a uniform grey of value `N`:
`out[0] = 180`, `out[1] = 169` (the blend), `out[15] = 15`, `out[179] = 179`, 180 frames, 6.000 s.

## The delivered lobby loop

`outputs/lobby/clamor_lobby_loop.mp4` — **56.0 s, 1280×720, 5.2 MB**, emitted by the same
`render.py` run that produces the 75 s cut. The dissolve sits at the **end** of the file (WI 1181, below),
so a single pass opens on clean material.

| | |
|---|---|
| Loop length | **56.0 s** (authored 56.616 s = the chorus-2 downbeat; the 2 s backwards search moved it 0.616 s earlier) |
| Video join | SSIM 0.911 vs keyframe-boundary norm 0.955 — gap **0.0445** (0.963 / 0.012 when re-encoded at crf 16, so most of that gap is bit allocation in the dissolve, not discontinuity) |
| Audio join | step 221 vs local maximum 1241 — **0.18×**, i.e. a far smaller step than ordinary music motion |
| Level across the dissolve | RMS 7693 → 1684 (**4.57×**) — see the correction below |
| Codec padding | **0 samples** |
| Cost | ~7 s wall, ffmpeg only, on top of the 38 s full render |

Doubled end to end (the file concatenated with itself, which is what a looping player decodes): 3360
frames = 2 × 1680, **no zero samples within ±10 ms of the join**, join step 0.305× the local maximum,
and the frames either side are visually continuous — the shot carries straight through the join and
only then dissolves into the opening shot.

## Three things worth keeping

**1. mp4/AAC gaplessness is a length question, not a codec verdict.** The 75 s cut decodes 353 samples
longer than its source FLAC — 8 ms of digital silence (RMS 0.4) that any looping player inserts at the
join. The 56.0 s loop decodes **exactly** its intended sample count. The difference: 56.0 s × 48 kHz =
2 688 000 samples = 2625 whole AAC frames of 1024, so the encoder has no partial frame to pad. A loop
length on the AAC frame grid is gapless in mp4; one off the grid is not. The tool measures and reports
this per output rather than assuming either way, and `--webm` (VP9/Opus) exists for the case where a
length cannot be moved onto the grid.

**2. A gate must compare like with like — twice over.** Both join gates were first written to compare
the join against its immediate neighbours, and both were systematically wrong for the same reason: the
two sides of a loop join sit in **different codec frames**.

- *Audio*: every other adjacent pair lives inside one AAC frame and shares its quantisation noise; the
  join pairs samples the encoder coded independently. A correctly-built wrap measured a join step of 96
  against a local maximum of 86 — failing a gate it should pass. A real discontinuity measures ~30×, so
  the bound became 2× and the report prints the ratio.
- *Video*: frame 0 is an IDR, coded independently of the P-frame chain the local norm comes from. The
  same two source frames score **0.983 inside one encode and 0.945 across the loop's keyframe**. So the
  gate also measures the best interior keyframe boundary in the same file and passes on either norm.
  Against that fair comparison the lobby join is *better* than an ordinary keyframe boundary (−0.0055),
  which is a far more convincing result than the 0.0414-against-0.05 the naive norm reported.

**3. Each gate needs a control that fails it alone.** The first negative control — a plain trim of a
level-ramped sine — turned out to cut at a zero crossing, so it failed the *level* check while being
invisible to the *discontinuity* check. A second control (constant level, trimmed at the sine's peak)
isolates the other gate. While fixing the discontinuity bound, a shadowed variable made a 123× level
jump report as 1.19×; the level control caught it in the same run. A gate only ever seen passing is not
evidence.

## Known limits

- **The loop is a second-generation encode.** It is built from the finished mp4, so its frames measure
  ~0.95 SSIM against the same frames in the full cut. Acceptable for a lobby background; the remedy, if
  it ever matters, is to fold the wrap into the assembly rather than run it afterwards.
- **The wrap returns to a quiet intro.** The song's first 4.4 s are instrumental lead-in, so the loop
  steps from full-band music down to the intro (RMS 1.69×). It is a dip, not a click, and it reads as a
  turnaround — but a loop *window* that skips the intro (a start offset, not just a length) would fix it
  properly and is deliberately not built here.
- **The envelope search hears rhythm, not harmony.** It matches short-time RMS, so it finds bar phase
  and cannot tell a chord change. Its score is reported; the ear is the last gate.

## Reproduce

```
python3 build_lobby.py                       # authors the manifest, loop block included
python3 render.py outputs/lobby/clamor_lobby.manifest.json --out outputs/lobby/clamor_lobby.mp4
# -> clamor_lobby.mp4 (75 s, the website cut) AND clamor_lobby_loop.mp4 (56 s, the lobby loop)
```

Standalone, on any rendered cut:

```
python3 loop_finish.py cut.mp4 --length 56.616 --crossfade 0.75 --search 2.0 --audio song.flac
```

38 checks in [`prototypes/test_loop.py`](../prototypes/test_loop.py) (`python3 test_loop.py`, GPU-free,
~9 s), plus 11 added to `test_manifest.py` and 5 to `test_render.py`.

## Update 2026-08-25 (WI 1181): the dissolve moved to the end, and one figure was wrong

Owner watched the loop, confirmed **the repeat is clean**, and noticed that the cut "adds a second from
the end to the beginning" — under the original arrangement the file *opened* mid-dissolve, on material a
first-time viewer had not seen. Asked whether that second could move to the end.

It can, for free. The wrap produces a **cycle**, and rotating a cycle gives the same cycle: `blend_at`
now chooses where the dissolve sits, and **`end` is the default**. A single pass opens on clean material
and closes by dissolving back toward its own opening; on repeat the two arrangements are identical.

**The discretisation is the whole trick.** A crossfade's weights run `0 → (N−1)/N`, so its first frame is
pure outgoing and its last still carries `1/N` of it. Under `start` that impure frame sits harmlessly
inside the file; a naive rotation would park it on the **final** frame — exactly where the loop join is
both measured and seen. So `end` does not reuse `xfade`: it blends with explicit weights running
`1/N → 1`, putting the exact frame at the boundary and the impure one at the *start* of the dissolve,
where a 1/22 ghost is invisible. Verified on the grey ramp: the file ends on frame 21 and opens on frame
22 — exactly adjacent, no ghost.

**Correction — the level step across the join is 4.4×, not the 1.69× first reported.** The old window
started at the file boundary and therefore lay *inside the crossfade*, so it measured the dissolve
rather than the music. Measuring pure material either side of the dissolve gives **7693 → 1684 (4.57×,
~13 dB)** on the delivered loop, and 4.39× on the arrangement the owner accepted. The step was always
there — the measurement was hiding it. The level bound moved with it: **8×**, now calibrated against an
owner-accepted loop (4.4×) and a plain trim (100×+) instead of being the invented 2× it started as. A
crossfade *bridges* a level step; it cannot remove one, and the tests now say so — wrapping a source
whose loud end meets its own near-silent start still fails the level check, correctly.

**One residual, measured not guessed.** The `end` arrangement's join scores 0.911 at crf 26 against 0.963
at crf 16: the final frame sits at the end of a fast dissolve, where the encoder spends fewest bits. The
content is continuous; the number is bit allocation. Left at crf 26 to match the full cut.
