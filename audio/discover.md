# Discover: Audio — generated SFX & music (Stable Audio 3, ACE-Step 1.5)

**Status:** completed

## Subject

Adding an **audio** asset track to the harness: AI-generated **sound effects** and **music/ambient**
for the games (DWA, Sounding, Scrapper's Soul). Candidate models, both present as **ComfyUI native
support** on `ai2`: **Stable Audio 3 Medium** (Stability AI) and **ACE-Step 1.5** (ACE Studio). As of
2026-06-23.

## Motivation

Decide whether audio is a viable harness track and on what terms: which model for which asset class,
whether **licensing + training-data provenance** clears commercial/redistribution use (the same gate
every other track is held to), and what the post-processing/import path looks like.

## Scope

- **In:** weights licenses *and* training-data provenance; ComfyUI integration; capabilities; the
  post/encode + import path; the games' actual audio needs.
- **Out:** building prototype graphs (next step); **vocal/lyric music** (style-mimicry exposure —
  noted, not pursued for shipped assets); hardware tuning on `ai2`.
- **Source gate:** license claims trace to the official license file / model card / vendor terms.
  Evidence labels per `skills/evidence.md`.

## Methodology & Sources

Inspected the three ComfyUI blueprints on `ai2` (`/opt/comfyui/blueprints/`) + core
`comfy/ldm/ace/ace_step15.py` to pin exact model repos and node graph. Verified licenses against the
upstream HF cards and the ACE-Step `LICENSE` file (not blog summaries). See **References**.

## Summary

Audio is a **viable track and a strong AI fit** — a better fit than the parked `rigged-avatars`
track. Both models are commercially usable with the cleanest provenance story of any models the
harness uses, and **integration is nearly free**: identical ComfyUI `/prompt` → `/history` → `/view`
path as the visual tracks, emitting `.wav` instead of `.png`. The real work is **post-processing**
(loudness/trim/loop/encode) + the import seam, not plumbing. Recommendation: **SFX via Stable Audio
3, music/ambient via ACE-Step 1.5**, SFX first.

## Findings

### Models present on `ai2` (Confirmed)

Native ComfyUI support; **weights not yet downloaded** into `models/` (auto-download from the HF
`resolve` URLs on first blueprint run — a setup step for the prototype phase, flagged not executed).

- **Stable Audio 3 Medium** — repo `Comfy-Org/stable-audio-3`:
  `stable_audio_3_medium.safetensors` (+ `_base`), encoders `qwen3.5_2b_bf16` + `t5gemma_b_b_ul2`.
  Nodes: `EmptyLatentAudio` → KSampler → `VAEDecodeAudio`. Two blueprints (Medium / Medium Base).
- **ACE-Step 1.5** — repo `Comfy-Org/ace_step_1.5_ComfyUI_files`: `acestep_v1.5_turbo.safetensors`,
  `ace_1.5_vae.safetensors`, encoders `qwen_0.6b_ace15` / `qwen_4b_ace15`. Nodes:
  `EmptyAceStep1.5LatentAudio` → `TextEncodeAceStepAudio1.5` → `VAEDecodeAudio`.

### Licensing & provenance

| Model | Weights license | Training-data provenance | Output ownership |
|---|---|---|---|
| **Stable Audio 3 Medium** | **Stability AI Community License** — free commercial **under $1M org revenue**; Enterprise above. *Stack also bundles **T5Gemma** under **Gemma Terms of Use**.* | **Fully licensed** (Confirmed): 1,278,902 recordings — 806,284 from **AudioSparx** (licensed) + 472,618 from **Freesound** (CC-0 / CC-BY / CCSampling+). | **You own outputs**, both tiers (Confirmed). |
| **ACE-Step 1.5** | **MIT** (Confirmed — `LICENSE` reads "MIT License", © 2026 ACEStep). Commercial + redistribution OK with notice. | Licensed + royalty-free/public-domain + **synthetic** (MIDI→audio). "Trained entirely on royalty-free non-copyrighted material" — **vendor claim** (Supported, not independently audited). | MIT — outputs unrestricted. |

- **Against the harness's gold "clean" (Apache/MIT) bar:** **ACE-Step 1.5 = MIT meets it outright**
  (the music model has the *cleaner license*); **Stable Audio 3 = Community License does not** — it's
  revenue-gated and drags in Gemma Terms. **But** the games are hobby/indie, far under $1M, outputs
  are owned, and Stable Audio 3 has the **best-documented provenance** of anything we use. So it's
  commercially fine *for this use*, with a documented **revenue ceiling + Gemma prohibited-use terms**
  to record in the gen log.
- **Provenance nuance (Hypothesis/Supported):** a clean *weights* license ≠ clean *outputs* for
  audio. Stable Audio 3's provenance is documented and specific (Confirmed-clean); ACE-Step's is a
  vendor claim (Supported). For either, **vocal/lyric tracks carry style-mimicry exposure regardless
  of license** → keep music to **instrumental/ambient** for shipped assets.

### Capabilities (Confirmed unless noted)

- **Stable Audio 3 Medium:** **48 kHz WAV**, variable length up to **~6 min**, does **SFX *and*
  music**. Fast (sub-few-seconds on a MacBook M4 per the card). Native SFX support + the Freesound
  half of its corpus *is* a foley/SFX library → the natural **SFX workhorse**.
- **ACE-Step 1.5:** music-specialized diffusion model; turbo variant present. **Confirmed to run on
  AMD Radeon** (AMD published a Ryzen-AI/Radeon ACE-Step 1.5 guide) → good fit for `ai2`. Best for
  **instrumental loops / ambient beds**.
- **`ai2` (AMD ROCm):** ACE-Step on AMD = Confirmed; Stable Audio 3 via ComfyUI-ROCm = Supported
  (general ROCm path, not yet run here).

### Integration & post-processing

- **Generation:** same `POST /prompt` → poll `/history/{id}` → `GET /view` API the visual harness
  already drives; nodes save `.wav`. No new client plumbing.
- **Post (the actual work):** an `audio/prototypes/optimize_audio.py` — the **ffmpeg** analogue of
  `blender_optimize.py`: EBU R128 loudness-normalize (`loudnorm`), trim silence, fades, author
  **loop points** for ambient beds (generate-long + crossfade), encode to **`.ogg` (Vorbis)** for
  Phaser/web (DWA, Scrapper) and **`.ogg`/`.wav`** for Bevy (`bevy_audio` supports ogg/wav/flac).
- **Seam:** unchanged — generated `.ogg`/`.wav` copied into each game's assets (same manual seam as
  sprites/glb today).

### Games' actual needs

- **DWA** (Phaser/web): UI clicks/confirms, thruster, mining laser, impact/collision, station hum,
  alerts → **mostly SFX** + maybe one ambient bed.
- **Sounding** (Bevy): engine rumble, structural creak/stress, RCS puffs, ambient space, UI → SFX +
  ambient. (Pairs with the deferred `bevy_hanabi` thruster *visual*.)
- **Scrapper's Soul** (isometric): ambience, footsteps, UI + a **music/ambient bed** → SFX +
  ACE-Step.

Net: the games want **SFX + ambient loops** far more than "songs" → reinforces **SFX-first**.

## Assessment

- **Feasibility: high.** Native ComfyUI support, both models run on `ai2`, integration mirrors
  existing tracks. The only real build is the ffmpeg post step + prompt/seed library.
- **Licensing: clears, with conditions recorded.** ACE-Step MIT is outright clean; Stable Audio 3 is
  fine for indie scale but its **revenue ceiling + Gemma terms** must live in the gen-log metadata.
  Add a **provenance column** to the audio gen log — audio risk is in the data, not the model card.
- **Risks:** (1) music **vocal** style-mimicry → restrict shipped music to instrumental/ambient;
  (2) Stable Audio 3 revenue gate if the games ever monetize at scale → re-evaluate then;
  (3) **seamless loops** are a creative/post problem, not a model feature → solve in `optimize_audio`.
- **Track shape:** one **`audio`** track with two sub-streams — `audio/prototypes/{sfx,music}` —
  sharing the same post/encode tooling and seam (mirrors `pbr-materials` / `3d-static-props`). Two
  top-level tracks also workable but they don't earn separate status.

## Recommendation

**Stand up the `audio` track.** Sequence: **(1) `sfx` via Stable Audio 3 Medium first** (best
provenance + biggest game need + native SFX); **(2) `music`/ambient via ACE-Step 1.5** as
instrumental-only, lower priority. Next concrete step: a SideQuest for the **`sfx` prototype** —
download the Stable Audio 3 weights on `ai2` (flagged setup step), build the generate script against
the blueprint graph, produce a first SFX set (UI click, thruster, impact, ambient hum) + the
`optimize_audio.py` post step, and import one into DWA to prove the seam end-to-end.

## Open Questions

- Exact ComfyUI node class IDs / widget params for the Stable Audio 3 + ACE-Step graphs (the
  blueprints use opaque UUID node types) — resolve by querying `/object_info` on `ai2` when wiring
  the prototype.
- Does Stable Audio 3 expose any native loop/seamless mode, or is crossfade-in-post the only path?
- Stable Audio 3 ROCm behaviour on `ai2` (VRAM, speed) — confirm on first run.
- `bevy_audio` format/feature flags actually enabled in Sounding — confirm at import.

## References

- Stable Audio 3 card — https://huggingface.co/stabilityai/stable-audio-3-medium
- Stability AI license — https://stability.ai/license
- Stable Audio 3 announcement — https://stability.ai/news-updates/meet-stable-audio-3-the-model-family-built-for-artistic-experimentation-with-open-weight-models
- ACE-Step 1.5 LICENSE (MIT) — https://github.com/ace-step/ACE-Step-1.5/blob/main/LICENSE
- ACE-Step 1.5 card — https://huggingface.co/ACE-Step/Ace-Step1.5
- ACE-Step 1.5 on AMD — https://www.amd.com/en/blogs/2026/commercial-grade-ai-music-generation-on-amd-ryzen-ai-and-radeon-ace-step-1-5.html
