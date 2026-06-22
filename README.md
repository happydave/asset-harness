# Asset Harness

Repeatable, AI-leaning pipelines that turn prompts/specs into **game-ready assets**, so the
games can lean on generation instead of manual art/CAD.

Initiative record & backlog (source of truth):
`tickets/docs/projects/asset-harness/project.md`.

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
| [2d](2d/) | Sprites w/ clean alpha, tiling textures, backdrops/skyboxes | 🟡 prototype validated |
| [pbr-materials](pbr-materials/) | Base color → normal / roughness / AO maps | ⚪ not started |
| [3d-static-props](3d-static-props/) | Image-to-3D textured meshes → cleanup → glTF | ⚪ not started |
| [mechanical-kit](mechanical-kit/) | Parametric Blender kit + AI surface/decals | ⚪ not started |
| [vfx](vfx/) | AI base particle textures + engine particle systems | ⚪ not started |
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
