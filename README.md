# Asset Harness

Repeatable, AI-leaning pipelines that turn prompts/specs into **game-ready assets**, so the
games can lean on generation instead of manual art/CAD.

**New here?** Start with the [Cold Start guide](docs/cold-start.md) — prerequisites and
a first-asset walkthrough.

Per-track status lives in the [tracks table](#tracks--status) below; each track's own
`README.md`, `discover.md`, and `findings/` hold the detail.

## How this repo is organized

Work is split into independent **per-asset-class tracks**. Each track is a self-contained
folder with its own discovery notes, prototypes, and findings, and moves through the same
lifecycle:

> **discovery** (what tools/models exist, do they run) → **prototypes** (try them, capture
> outputs + provenance) → **harness** (a documented, repeatable procedure/script).

Outputs are **engine-agnostic**. Consuming games (Phaser/TS, Bevy/Rust, Ebitengine/Go) import
them through a thin, per-engine downstream step that lives in the game repo, not here.

The generation harness is **Python** (ComfyUI's API is Python-native; workflows export as
API-JSON).

## Tracks & status

| Track | Purpose | Status |
|-------|---------|--------|
| [2d](2d/) | Sprites w/ clean alpha, tiling textures, backdrops/skyboxes | 🟢 ships + station kit + spider-miner body; in-game |
| [pbr-materials](pbr-materials/) | Base color → normal / roughness / AO maps | 🟢 hull + structural + biome terrain libraries; Bevy-ready, in-game |
| [3d-static-props](3d-static-props/) | Image-to-3D meshes + heightmap terrain → cleanup → glTF | 🟡 heightmap-displacement terrain (clean); MoGe=props; TripoSR env-blocked |
| [mechanical-kit](mechanical-kit/) | Parametric Blender kit + AI surface/decals | 🟡 20 AI-textured parts in `parts/` (rover + rocket-domain + fittings), mount-at-origin, for Sounding WI 608 |
| [vfx](vfx/) | AI base particle textures + engine particle systems | 🟡 thruster flame sprites (plume/puff/spark) |
| [audio](audio/) | Generated SFX + music/ambient → ffmpeg post → engine | 🟢 SFX (Stable Audio 3) + ambient music (ACE-Step) → ffmpeg loop post; thruster set in DWA |
| [rigged-avatars](rigged-avatars/) | AI mesh + auto-rig (deferred) | ⚪ not started |

Legend: ⚪ not started · 🟡 in progress · 🟢 repeatable harness exists

## Conventions

- **Every prototype records provenance.** Copy [`_template/findings.md`](_template/findings.md)
  into a track's `findings/` and fill it in: model/workflow/version, prompt/seed/params, the
  **hardware it ran on**, and a `works / partial / fails` verdict. AMD failures are recorded,
  not hidden.
- **Every generation records its license chain.** Track the license of the base model **and**
  every LoRA/ControlNet used; the output's effective license is the *most restrictive link*.
  This gates which assets can go into a "clean" (commercially redistributable) pack later.
- **Local-first.** Try ComfyUI locally before reaching for hosted APIs; if a hosted service is
  used, note why local fell short.
- Large generated outputs and model weights are git-ignored (see `.gitignore`); commit
  *representative samples* small enough to be useful, plus the findings that reproduce them.

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or
  <http://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <http://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in the work by you, as defined in the Apache-2.0 license, shall be
dual licensed as above, without any additional terms or conditions.

**This license covers the harness itself** — the scripts, workflows, and docs in
this repo. It does **not** relicense generated asset outputs: each generated asset
carries its own effective license, determined by the *most restrictive link* in its
model/LoRA/ControlNet chain (see [Conventions](#conventions)). Check an asset's
`findings.md` before redistributing it.
