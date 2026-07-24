# Findings: Clamor lobby-loop walking skeleton — manifest → renderer → 75 s video, end to end

**Date:** 2026-07-24
**Track:** music-video (composite)
**Verdict:** works — the end-to-end pipeline runs from a shot-list manifest to a watchable 75 s Clamor
lobby loop; the manifest→pure-renderer architecture held; output is 7.1 MB (well under the `go:embed`
budget). Owner `[human]` review is the real gate on whether to build the full gated pipeline.

## Goal

[WI 1004](../../../../tickets/docs/pending/1004-ah-music-video-walking-skeleton/workitem.md): prove the
music-video artifact before building the process around it. One song → timeline → **shot-list
manifest** → stills + one hero clip → ffmpeg assembly → a ~60 s Clamor lobby loop. No gate machinery,
no candidate loop. The durable contribution is the **manifest schema**, decided here by contact with a
real edit.

## Tooling

- **Song + timeline:** `clamor_hold_the_line_seed701.flac` (75.0 s, 16 lines) + its post-hoc timeline
  (WI 1001). Reused, not regenerated.
- **Stills:** **Z-Image `base`** (`z_image_bf16` + `qwen_3_4b` + `ae`) on `ai2` — 5 new (seeds 101–105,
  1280×720, 20 steps, cfg 4, euler/simple, shift 3) + 2 reused vetted WI 1018 stills.
- **Hero clip:** the WI 1018 `clip1_nolora_char_720p.mp4` (fp8 Wan2.2 i2v, no-LoRA, 720p), interpolated
  16→30 fps with `interpolate.py` (ffmpeg `minterpolate` mci — the WI 1019 smoothness fix).
- **Assembly:** direct-subprocess ffmpeg 6.1.1 on the workstation (`ai2` has no ffmpeg).
- **New prototypes:** `manifest.py` (schema + partition + validate + io), `render.py` (pure renderer),
  `build_lobby.py` (authored driver), `test_manifest.py` (17 checks, all green).

## Licensing (per `../license-lane.md`)

| Artifact | Licence | Commercial? | Notes |
|---|---|---|---|
| ACE-Step 1.5 (song, WI 1001) | Apache-2.0 weights | yes | vocal, under the standalone-media-artifact lane |
| Z-Image base + qwen_3_4b + ae | Apache/MIT (2D clean stack) | yes | stills |
| Wan2.2 i2v (hero clip, WI 1018) | Apache-2.0 | yes | interpolation is ffmpeg, no model |

- **Vocal flag:** yes — a vocal song. Permitted: this is a **standalone media artifact** (a lobby
  video), the lane's bounded exception; it is **not** a shipped in-game audio asset.
- **Lyric provenance:** WI 1001's original authored lyrics; the lyrics gate was cleared there.
- **Prompt hygiene:** all 5 new image prompts name no franchise, artist, or real person — generic
  survival-horror scenes in the house style. Z-Image's negative prompt bars text/watermark; inspected
  output carries **no title-card text**.

## Inputs

- **Manifest:** [`samples-2026-07-24-lobby-skeleton/clamor_lobby.manifest.json`](samples-2026-07-24-lobby-skeleton/clamor_lobby.manifest.json)
  — 8 shots × 2 lyric lines, verse/chorus/verse/chorus; hero `video` on chorus shot 2 (23.90–29.25 s ≈
  the clip's 5.06 s). Each shot: `{index, section, lines[], t_start, t_end, kind, prompt, asset, kb}`.
- **Seeds:** 101–105 (new stills). **Ken-Burns:** per-shot zoom in/out/none + pan, in the manifest `kb`.

## Steps

1. `python3 build_lobby.py` — partitions the timeline into 8 shots, authors creative fields, generates
   the 5 missing stills on `ai2`, interpolates the hero clip, emits the validated manifest.
2. `python3 render.py outputs/lobby/clamor_lobby.manifest.json --out outputs/lobby/clamor_lobby.mp4` —
   pure render: per-shot zoompan/clip segments → xfade chain → audio mux → web mp4.

## Result

- **`clamor_lobby.mp4` — 75.0 s, 1280×720, H.264/yuv420p + AAC, 7.1 MB.** (Gitignored per repo
  convention; owner reviews it locally. Representative frames + the manifest are committed under
  `samples-2026-07-24-lobby-skeleton/`.)
- **Sample:** [`lobby_contact_8shots.png`](samples-2026-07-24-lobby-skeleton/lobby_contact_8shots.png)
  (all 8 shots), plus [`shot01_silent_city.png`](samples-2026-07-24-lobby-skeleton/shot01_silent_city.png),
  [`shot04_flare_stairwell.png`](samples-2026-07-24-lobby-skeleton/shot04_flare_stairwell.png),
  [`shot07_dawn_resolve.png`](samples-2026-07-24-lobby-skeleton/shot07_dawn_resolve.png).
- **`[agent]` assessment (what I could verify by inspection):** every shot's image is on screen across
  its lyric window in order; the hero clip plays in slot 2; Ken-Burns framings differ from the source
  stills (the move is present); crossfades blend (boundary frames are non-black); `blackdetect` finds
  **no black segments** across the full 75 s; the five Z-Image stills are opaque, coherent, on-brief,
  and free of the title-card-text / invented-background failure modes. The stills are genuinely strong —
  the flare/stairwell and dawn-resolve shots in particular read as intentional concept art.
- **What worked:** the manifest→pure-renderer split — `render.py` contains no creative decisions, so the
  whole edit is a function of the committed JSON. Regenerating one shot is `rm assets/shotNN.png` +
  re-run `build_lobby.py` + re-run `render.py`; nothing else changes.
- **What is skeleton-grade (honest):** (1) **loop seam** — the song has vocals and a ~7 s instrumental
  outro, so the 75 s clip does not audio-loop click-free; a lobby loop wants either a shorter
  instrumental-tailed cut or a crossfaded loop point. (2) **75 s, not ≤60 s** — the song is a fixed
  artifact; a tighter cut is a finish task. (3) **Ken-Burns feel** is uniform (slow zoom/pan); a real
  edit would vary rate to the music. (4) The **hero clip is a survivor on a chorus** — a small
  subject/section mismatch chosen to keep the hero window ≈ the clip length.

## Repeatability

Deterministic given the seeds and the manifest: `render.py` is a pure function of the manifest + assets;
`build_lobby.py` is idempotent (an asset on disk is left alone). `test_manifest.py` gates the schema.

## Recommendation (AC 4 — feeds the owner `[human]` gate)

**Proceed to the gated pipeline is justified on quality** — the skeleton clears the bar: the stills are
strong, the edit is coherent, assembly is clean and tiny, and the manifest architecture makes the gates
cheap to add. The final "good enough" call is the owner's (`[human]`).

What the gated pipeline should add over this skeleton, in priority order:
1. **A loop-seam finish step** — the single biggest gap between "watchable clip" and "lobby loop":
   pick an instrumental loop point or crossfade the head/tail; target ≤60 s.
2. **The candidate/pick gates** — ACE-Step `batch_size` for 3–5 song candidates and a Z-Image seed sweep
   per shot, with the owner picking; the skeleton took the first roll of everything.
3. **A shot-list review gate** on the manifest before render (it is already the reviewable artifact).
4. **Ken-Burns variation** keyed to section (push in on choruses, drift on verses) and possibly a second
   hero clip on the second chorus.

## Next

- Owner watches `clamor_lobby.mp4` (muted and with sound) and rules on 1–4 above.
- If GO: a normal `Plan` for the gated pipeline (this skeleton is the reference), not an extension here.
- WI 1004 delivered the manifest schema + the pure renderer; both are reusable as-is.
