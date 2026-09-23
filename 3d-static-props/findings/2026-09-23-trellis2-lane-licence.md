# Findings: the licence record of the ComfyUI TRELLIS.2 lane, and DINOv3 attribution

**Date:** 2026-09-23 · **Work item:** WI 1749 (tickets) · **Lane:** ComfyUI v0.34.6 core nodes,
`prototypes/trellis2-comfyui/` · **Sources:** fetched on the date above. The fetched copies are in
`tickets/tmp/1749/`. The machine-readable rows are `prototypes/trellis2-comfyui/lane_licences.json`.

These are readings of licence texts. They are not legal advice. Re-read a source before relying on
it: Meta's licence lets Meta change it "effective immediately" (§8).

## Verdicts

- **Every model the lane loads is MIT by its source's declared licence, except the image
  conditioner.** The conditioner is DINOv3
  (Meta's DINOv3 License) with a NAF upsampler (valeo.ai, Apache-2.0) in the same file. Both arms load
  it. Confirmed from each source's own licence file or repository metadata (table below).
- **"Built with DINOv3" appears in one of Meta's two texts, not both.** Meta's web page (dated
  2025-08-14) has it. The `LICENSE.md` in Meta's GitHub repository and in its gated Hugging Face
  repositories (2025-08-19, byte-identical) does not. Confirmed by fetching all three.
- **Where it would appear:** "prominently … on a related website, user interface, blogpost, about
  page, or product documentation" (Meta's page, §1.b.i(B)). Both texts attach their redistribution
  duties to distributing, or making available to a third party, "the DINO Materials, or any
  derivative works thereof". Both define DINO Materials as Meta's documentation, models, code and
  weights, and both name "output and results" separately (§3, §5.b).
  - **Reading:** a generated asset is an output, so shipping one does not trigger the duty.
    Distributing the lane's weights, or the lane itself, would.
  - The sidecar carries the credit line anyway (see Recording), so a product can show it whichever
    reading the owner takes (O2).
- **The conditioner reached the lane through a relabelling mirror.** `Comfy-Org/Pixal3D` serves the
  DINOv3+NAF file ungated under a repository-wide `license: mit` tag, with no licence or notice file.
  WI 1197 had rejected exactly that kind of mirror for this lane's licence record. Both Meta texts
  bind by use ("By … using or distributing any portion … you agree to be bound"), so the DINOv3
  License governs our use whatever the tag says. Whether the estate should hold Meta's own grant is
  O1.
- **Outputs are recorded per asset** in a sidecar, `<glb>.lane.json`, whose `license_record` and
  `provenance` validate against the contracts schema's own definitions. contracts-3 has no class
  for a single static prop, so these two blocks will move unchanged into one when it gains that
  class.

## The components

| File (both arms unless noted) | From (revision) | Upstream and licence |
|---|---|---|
| `clip_vision/dino_v3_L_naf_fp32` | `Comfy-Org/Pixal3D` (`f37641be`), tagged MIT, ungated | DINOv3 ViT-L/16 (`facebook/dinov3-vitl16-pretrain-lvd1689m`, gated; DINOv3 License) and NAF (`valeoai/NAF`, Apache-2.0; no separate licence was found for the weights, so Apache-2.0 is inferred) |
| `diffusion_models/trellis_2_int8_convrot` (TRELLIS.2 arm) | `Comfy-Org/TRELLIS.2` (`430a9d09`) | `microsoft/TRELLIS.2-4B`, MIT |
| `vae/trellis_2_shape_vae_bf16`, `vae/trellis_2_texture_vae_bf16` | `Comfy-Org/TRELLIS.2` (`430a9d09`) | `microsoft/TRELLIS.2-4B`, MIT |
| `diffusion_models/pixal3d_int8_convrot` (Pixal3D arm) | `Comfy-Org/Pixal3D` (`f37641be`) | `TencentARC/Pixal3D`, MIT ("Copyright (c) 2026 Tencent") |
| `geometry_estimation/moge_2_vitl_normal_fp16` (Pixal3D arm) | `Comfy-Org/MoGe` (`14849852`) | `Ruicheng/moge-2-vitl-normal`, MIT (base DINOv2-large, Apache-2.0) |
| `background_removal/birefnet` | `Comfy-Org/BiRefNet` (`25511f87`) | `ZhengPeng7/BiRefNet`, MIT |
| tooling: ComfyUI | v0.34.6 (`8fed378`) | GPL-3.0. On the common reading (WI 1601) the GPL does not reach outputs, and distributing the tool would |

How the conditioner file was identified:
- Its 452 tensors are the transformers `DINOv3ViTModel` layout (`embeddings.register_tokens`,
  `layer.0`–`layer.23`) plus `naf.*`.
- ComfyUI's `Pixal3DMultiViewConditioning` tooltip (v0.37.2) calls it "DINOv3 ViT-L/16 ClipVision
  with bundled NAF weights".
- Official Pixal3D loads the same pair at run time: `DINOv3ViTModel` from
  `camenduru/dinov3-vitl16-pretrain-lvd1689m`, and NAF by `torch.hub.load("valeoai/NAF", …)`.
- Pixal3D's NOTICE names neither DINOv3 nor NAF; it lists DINOv2, TRELLIS.2, Direct3D-S2 and MoGe.

## The two DINOv3 texts

| | GitHub `LICENSE.md`, also bundled in Meta's gated HF repositories | Meta's web page (the HF card's `license_link`) |
|---|---|---|
| Date | Last Updated 2025-08-19 (first import 2025-08-14, identical in substance) | 2025-08-14 |
| §1.b.i | redistribute under the Agreement, with a copy of it | the same, **plus (B)** "prominently display 'Built with DINOv3' …" |
| Survival clause | "Sections 3, 4 and 7" (fixed by PR #76) | "Sections 5, 6 and 9" (the unfixed numbering) |
| Common to both | acknowledge DINO Materials in published research; trade controls; no ITAR, military, nuclear, espionage or weapons end uses; no reverse engineering; termination on breach; binding by use | |

A research sweep on 2026-09-23 (not re-opened here; Supported) found:
- no Meta source saying which text governs (dinov3 issues #28 and #31 have no settling reply);
- no public discussion of Comfy-Org's ungated, MIT-tagged redistribution (its HF discussions;
  ComfyUI PR #14718);
- one other redistributor, `raven38/pixal3d-*`, relabelling its DINOv3 part `dinov3-license` apart
  from its MIT files (image-to-3dlab issue #45).

## Recording: the sidecar

`lane_sidecar.py GLB API_GRAPH --models DIR --checkout DIR [--custom-nodes a,b]` writes
`<GLB>.lane.json`:

- `asset`: the file name, bytes and sha256.
- `license_record`: status `conditional`, `commercial_in_game` and `standalone_redistributable`
  both true, `source.kind` `local-generation`.
  - `text` names the licences, the GPL reading, the credit line "Built with DINOv3" whenever the
    conditioner is loaded, and the O1 condition.
  - `components` gives each file's source and parts.
- `provenance`: `provider-nondeterministic`, because a rerun does not reproduce the bytes (the raw
  decode varies). The recipe carries the ComfyUI version and commit, every node's literal inputs,
  the seed, and the sha256 of every model file and of the custom nodes the run loaded.

The writer refuses (exit 2) a graph that loads a file with no row in `lane_licences.json`, a graph
with more than one generator, or a file missing on disk. A record failing the schema exits 1.
Nothing is written in either case.

Sidecars for WI 1761's two textured GLBs are in `samples-2026-09-23/`. Their dependency hashes
match `sha256sum` of the files on `gtr`, and each model's size matches its HF listing.

## Owner decisions

- **O1 — the conditioner's provenance.**
  - **Recommended:** get access to Meta's gated `facebook/dinov3-vitl16-pretrain-lvd1689m`. Then
    compare the file's DINOv3 tensors with Meta's release, and its `naf.*` tensors with valeo's
    `naf_release.pth`. If they match, the estate's use rests on Meta's grant and valeo's licence,
    not on a mirror's tag.
  - Alternatives: accept the mirror, since use binds either way; or ship no lane assets until
    access is granted.
- **O2 — "Built with DINOv3" on products that ship lane assets.**
  - **Recommended:** show it in credits or product documentation. It costs nothing and meets the
    stricter text on the stricter reading.
  - Alternative: omit it, on the reading that assets are outputs.

Until O1 is decided, sidecars say `conditional`.
