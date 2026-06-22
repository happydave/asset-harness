# Findings: TripoSR + MoGe first run (both blocked on missing model weights)

**Date:** 2026-06-22
**Track:** 3d-static-props
**Verdict:** **MoGe ✅ runs on gfx1201 — first working local 3D on AMD (clean MIT; 2.5D relief).**
TripoSR blocked on a Flowty node↔model version mismatch (env, *not* ROCm). Hunyuan landed under
the wrong loader path. (Run 1 below was pre-install; Run 2 is post-install.)

## Goal

Test the clean (MIT) local 3D paths on `ai2`: TripoSR (image→mesh) and MoGe (image→2.5D relief),
on the `prop_crate.png` concept. Harnesses: `run_triposr.py`, `run_moge.py` (reuse the
`run_hunyuan3d.py` HTTP helpers).

## Result

Neither reached GPU compute — both failed at **model load**, so this says nothing yet about ROCm.

### TripoSR — model not installed

`TripoSRModelLoader`'s combo lists only the SDXL/SD3.5 checkpoints. The Flowty node does
`torch.load(get_full_path("checkpoints", model))`, i.e. it loads whatever file you select as the
TripoSR pickle — passing `ilustmix_v9.safetensors` →
`KeyError: 164` in the unpickler (it's an SDXL safetensors, not the TripoSR ckpt). The actual
TripoSR weights are not present.

**Fix:** download `model.ckpt` from `stabilityai/TripoSR` → `ComfyUI/models/checkpoints/`
(it'll then appear in the loader combo; select it). Restart ComfyUI.

### MoGe — model not installed

`/prompt` 400: `value_not_in_list — model_name: 'moge_2_vitl_normal_fp16.safetensors' not in []`.
`LoadMoGeModel`'s option list is empty → no MoGe weights present.

**Fix:** place `moge_2_vitl_normal_fp16.safetensors` in the MoGe model folder the node scans
(e.g. `ComfyUI/models/MoGe/`). Restart ComfyUI.

## Status of the three local 3D paths (after weights installed)

| Model | Nodes | Weights | ROCm (gfx1201) | License |
|---|---|---|---|---|
| **MoGe** | ✅ | ✅ `geometry_estimation/` | **✅ runs** | MIT ✅ |
| TripoSR | ✅ | ✅ `checkpoints/TripoSR-model.ckpt` | ❌ blocked **before** GPU (version mismatch) | MIT ✅ |
| Hunyuan3D 2.0 | ✅ | ⚠️ in `diffusion_models/` (wrong loader) | untested | Tencent (restricted) |

## Run 2 — weights installed (2026-06-22)

- **MoGe ✅** — `run_moge.py` succeeded on the crate. Output: a **textured 2.5D relief mesh**
  (`moge_00001_.glb`, ~25 MB, 1 mesh, **563,686 verts / 1,123,370 tris**, 1 image + 1 material).
  The normal render (`samples-2026-06-22/moge_crate_normal.png`) clearly reconstructs the crate's
  visible faces/latches/handle + the white background as a flat ground plane. **This is the first
  3D generation confirmed running on `ai2`'s gfx1201 (ROCm).** Caveats: it's **single-view** (no
  back face — a heightfield from the camera; great for terrain/backdrops, partial for a discrete
  prop) and **very high-poly** → needs aggressive decimation (+ ground-plane crop) before Bevy.
- **TripoSR ❌** — model file now loads, but `load_state_dict` fails: the ckpt uses HF-ViT keys
  (`image_tokenizer.model.encoder.layer.N.attention.attention.query…`) while the Flowty node's TSR
  code expects `image_tokenizer.model.layers.N.attention.q_proj…`. A **node/model/transformers
  version mismatch in the Flowty stack on `ai2`** — fails *before* any GPU compute, so it's an env
  fix (align the `ComfyUI-Flowty-TripoSR` revision / `transformers` / model revision), not ROCm.
- **Hunyuan3D** — the file is `diffusion_models/hunyuan3d-dit-v2-0-fp16.safetensors`, but the
  image-to-3D template's `ImageOnlyCheckpointLoader` scans `checkpoints/`. Different loader/path;
  deprioritized given the license. (Would need the right loader or a checkpoints/ copy.)

**Net:** ROCm *can* run 3D geometry nets on gfx1201 (MoGe proves it) — encouraging for TripoSR/
Hunyuan once their env issues are sorted. We now have **one working clean (MIT) local 3D path**
(MoGe, 2.5D). A full-object clean path still wants TripoSR's env fixed, or TRELLIS on the NVIDIA box.

## Next

- Install any of the three weights above and re-run the matching harness — that is the actual
  gfx1201 ROCm test (the real open question). Start with **TripoSR** (clean MIT, lowest fidelity)
  or **MoGe** (clean MIT, instant terrain/relief).
- If a model loads but a custom op fails on ROCm, that's the data point to capture (retry on the
  RTX 5070 workstation).
