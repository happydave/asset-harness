# Delivery target: Slack custom emoji

A **delivery target** spec describes what a *destination* demands of a file, independently of which
track produced it. Every other doc in this repo is organised by asset class (what we make) or by
consuming game (who imports it); this one is organised by where the file is going. Read it before
producing an emoji or any small icon for Slack, and extend it — do not fork it — for the next target.

The rule this document exists to enforce: **what Slack states and what the internet repeats are not
the same set of facts, and only one of them is a requirement.**

## Verified constraints

Fetched from Slack's own documentation on **2026-09-01**. Quoted verbatim; re-verify before treating
any of it as current.

| Constraint | What Slack says | Source |
|---|---|---|
| Shape, size, background | "Square images under 128KB and with transparent backgrounds work best." | [Add custom emoji and aliases to your workspace](https://slack.com/help/articles/206870177-Add-custom-emoji-and-aliases-to-your-workspace); the same sentence appears in [`admin.emoji.add`](https://docs.slack.dev/reference/methods/admin.emoji.add) |
| Formats | "Images can be in JPG, PNG, or GIF format." | Help article |
| Animation | "GIFs can include up to 50 frames." | Help article |
| Name case | "The name of the emoji to be added (using lower-case letters only)" | `admin.emoji.add` |

**Upload rejections** are named in the API reference, and the names tell you which limit you hit:

| Error | Means |
|---|---|
| `error_bad_wide` | the image's width/height was rejected |
| `error_too_big` | the file exceeded the size limit |
| `too_many_frames` | an animated image exceeded the frame limit |
| `error_lower_case_names_only` | the name contained capital letters |

Slack publishes the *existence* of the width/height and size limits through these errors without
publishing their thresholds, which is why the numbers below are conventions rather than quotations.

## What Slack does not state

Two figures are near-universal in third-party guides and appear **nowhere** in any Slack page checked:

- **128 × 128 pixels.** Slack states only "square". We target 128 × 128 anyway — it is square, it is
  what every emoji tool produces, and it is comfortably inside the byte cap — but it is a
  **convention we adopt**, not a requirement we were given.
- **A 22–32 px display size.** Slack publishes no render size. Design and test against a *range*
  rather than a figure; this repo checks 16 / 22 / 32 px, which brackets the reported range and adds
  a pessimistic case.

Treat both as working assumptions. If a rejection or a rendering ever contradicts them, correct this
section — that is what it is for.

**Hyphens in names are unverified.** Lower-case-only is confirmed; whether `:like-this:` is accepted
is not stated anywhere checked. Underscores (`:like_this:`) match Slack's own built-in emoji naming
and are the safe fallback if a hyphenated name is refused.

## Target specification

What to produce, absent a reason to deviate:

- **128 × 128 px, square.** Pad to square with transparency — never stretch. Slack forces a
  non-square image into a square frame, and a squashed subject is a distorted subject.
- **PNG with a real alpha channel.** Transparency is what lets one file sit on both the light and the
  dark theme. JPG cannot do it; GIF's 1-bit transparency gives hard edges.
- **Under 131072 bytes** (128 KB, exclusive). At 128 px this is not close to binding — a file
  approaching it usually means an opaque background was retained by mistake.
- **Static: a single frame, not an APNG.** Animation is a GIF, and a different job.
- **Lower-case name.**

Animated targets additionally: **GIF, at most 50 frames**, inside the same square and byte cap. The
byte cap applies to the whole animation, so frame count, palette and dithering are design inputs from
the first frame, not export settings chosen at the end.

## Design guidance at display size

*Ours, not Slack's* — established by producing a set and inspecting it small
([2d findings, 2026-09-01](../../2d/findings/2026-09-01-world-of-magic-emoji.md)). An emoji is shown
at roughly a fifth of the size it is stored at, so:

- **Judge it at display size, not at 128 px.** Everything looks fine at 128 px. Render candidates at
  16/22/32 px on both a light and a dark background and decide from that; `emoji_post.py sheet`
  builds exactly that contact sheet.
- **A dark subject fails on the dark theme.** A black top hat is the clearest possible emoji at 22 px
  on white and an unreadable blob at 22 px on Slack's dark background. Brightening the subject —
  same composition, purple instead of black — fixed it outright. This is the single most likely way a
  good-looking emoji fails in practice, and it is invisible if you only ever check one background.
- **One subject, bold silhouette, few internal details.** Interior detail is gone by 22 px; the
  outline is all that survives.
- **No lettering.** Text degrades to noise at display size, and generative models add it unbidden.
- **Strong colour separation beats fine rendering.** The candidates that read smallest were the ones
  with two or three saturated colours in large blocks.

## Producing one in this repo

The 2d track carries the tooling:

- [`2d/prototypes/generate_emoji.py`](../../2d/prototypes/generate_emoji.py) — Z-Image txt2img joined
  to the BiRefNet alpha tail, several concept directions × several seeds, one recipe JSON per
  candidate. Its style anchor documents two clauses that are load-bearing for the *matte*: the
  subject must be small inside a white frame (or the matting model finds no background and returns an
  empty mask) and it must be saturated (a pale subject on white mattes down to its outlines).
- [`2d/prototypes/emoji_post.py`](../../2d/prototypes/emoji_post.py) — `build` fits candidates to the
  target, `check` gates them against this spec and exits non-zero on violation, `sheet` renders the
  display-size contact sheet.
- [`2d/prototypes/test_emoji_post.py`](../../2d/prototypes/test_emoji_post.py) — the gate's own
  regression tests; synthetic fixtures only, no ComfyUI or network needed.

## Uploading

Uploading is an **owner action** and is deliberately not automated here: it needs workspace
credentials this repo does not hold and should not acquire. Slack's *Add custom emoji* help article
is the procedure. Hand over the file and the intended name; the workspace does the rest.

---

*Not vendor advice.* This records what Slack's documentation said on the date above. Vendor limits
change without notice, and a rejected upload is better evidence than this page.
