# Findings: <short title>

**Date:** YYYY-MM-DD
**Track:** <2d | pbr-materials | 3d-static-props | mechanical-kit | vfx | rigged-avatars>
**Verdict:** <works | partial | fails>

## Goal

What asset class / outcome was this experiment trying to produce, and for which game(s)?

## Tooling

- **Base model:** <name + version/hash>
- **LoRA(s) / ControlNet / adapters:** <name + version, each>
- **Workflow / nodes:** <ComfyUI workflow file, custom nodes + versions>
- **Other software:** <rembg, Blender, DeepBump, hosted API, etc. + versions>

## Licensing (commercial / redistribution)

Track the license of **every** model artifact in the chain — base model, each LoRA, each
ControlNet/adapter. The effective license of the output is the **most restrictive link**.
(Separately note: AI-generated images may not be copyrightable in some jurisdictions — that
governs whether *you* can claim the output, not whether you may *use* the model.)

| Artifact | License | Commercial? | Redistribute? | Source |
|----------|---------|-------------|---------------|--------|
| <base>   | <...>   | <yes/no>    | <yes/no>      | <url>  |

- **Effective output license:** <most-restrictive result>
- **Safe for a clean/commercial asset pack?** <yes / no / prototype-only>
- **Notes:** <revenue caps, "no monetized inference service" clauses, attribution required, ...>

## Hardware

- **Machine / GPU:** <e.g. workstation RTX 5070 | gfx1151 Strix Halo | gfx1201 R9700>
- **Stack:** <CUDA x.y | ROCm x.y, driver, OS>

## Inputs

- **Prompt(s):** <...>
- **Seed(s):** <...>
- **Key params:** <steps, cfg, sampler, resolution, ControlNet/LoRA/IPAdapter refs, ...>

## Steps

1. <reproducible steps — link the workflow file / script>

## Result

- **Sample output(s):** <relative paths to committed samples>
- **What worked / quality notes:** <...>
- **What failed / artifacts:** <...>

## Repeatability

- Deterministic given seed? Style-consistent across runs? Manual cleanup required?

## Next

- <follow-ups, or what to fold into the repeatable harness>
