# Track: 3d-static-props

**Status:** 🟡 discovery done; see [discover.md](discover.md). ⚠️ 3D breaks the clean lane —
Hunyuan3D 2.0 (native ComfyUI, harness ready) is high-quality but **Tencent Community License**.
**Clean plan, routed by hardware:** TripoSR (MIT) on `ai2` first (low friction, best ROCm odds);
TRELLIS.2 (MIT, hero quality) on the NVIDIA workstation (CUDA-heavy, AMD-hostile).

**ROCm result (2026-06-22, see [findings](findings/2026-06-22-triposr-moge-test.md)):**
**MoGe ✅ runs on gfx1201** — first working local 3D on AMD (clean MIT), a textured **2.5D relief**
(single-view, very high-poly → needs decimation; good for terrain/backdrops). **TripoSR ❌** is
blocked *before* the GPU by a Flowty node↔model `state_dict` version mismatch (env fix, not ROCm).
Hunyuan3D weights landed under the wrong loader path (deprioritized — license). So: one working
clean (MIT) 2.5D path; a clean full-object path still needs TripoSR's env fixed or TRELLIS on NVIDIA.

## Purpose

Image-to-3D for static, organic/greeble props (Sounding: computers, debris, rocks, trees).
Single concept image → textured mesh → cleanup → glTF for Bevy.

## Approach (to validate)

- **Local-first:** Hunyuan3D 2.x in ComfyUI (single image → textured mesh).
  ⚠️ Some 3D-gen pipelines use CUDA-only custom ops — verify on the workstation RTX 5070 and
  record AMD (gfx1151/gfx1201) results as data; fall back to hosted (Tripo/Meshy/Rodin) only
  if local proves unworkable.
- **Cleanup stage:** remesh/decimate (Instant Meshes / Blender) → UV → export glTF.

Best suited to organic/irregular shapes — *not* clean modular mechanical parts (see
[mechanical-kit](../mechanical-kit/)).

## Contents

- `findings/`, `prototypes/` (created when work starts; use
  [`../_template/findings.md`](../_template/findings.md)).
