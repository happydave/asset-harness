# Findings: TripoSR + MoGe first run (both blocked on missing model weights)

**Date:** 2026-06-22
**Track:** 3d-static-props
**Verdict:** blocked — node packs installed, **model weights absent**; **ROCm still untested**.

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

## Status of the three local 3D paths

| Model | Nodes on `ai2` | Weights on `ai2` | ROCm (gfx1201) | License |
|---|---|---|---|---|
| Hunyuan3D 2.0 | ✅ | ❌ (`hunyuan3d-dit-v2_fp16` → checkpoints/) | untested | Tencent (restricted) |
| TripoSR | ✅ | ❌ (`model.ckpt` → checkpoints/) | untested | MIT ✅ |
| MoGe | ✅ | ❌ (`moge_2_vitl_normal_fp16` → MoGe/) | untested | MIT ✅ |

All harnesses are written and correct against the node schemas; **each is one model-file away from
the real ROCm test.**

## Next

- Install any of the three weights above and re-run the matching harness — that is the actual
  gfx1201 ROCm test (the real open question). Start with **TripoSR** (clean MIT, lowest fidelity)
  or **MoGe** (clean MIT, instant terrain/relief).
- If a model loads but a custom op fails on ROCm, that's the data point to capture (retry on the
  RTX 5070 workstation).
