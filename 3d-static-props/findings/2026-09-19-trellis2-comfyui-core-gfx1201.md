# TRELLIS.2 on ComfyUI core nodes, gfx1201 — 2026-09-19

Spike WI 1600. Full record and evidence:
`tickets/docs/pending/1600-ah-spike-trellis2-comfyui-core-rocm/spike.md`.
Scaffolding to reproduce: `../prototypes/trellis2-comfyui/`.

## What was established

ComfyUI 0.34.6's **core** TRELLIS.2 nodes run on the 32 GiB R9700 (gfx1201) on `ai2`, in a
digest-pinned rootless-podman container, without touching the shared `comfyui.service`. About
**270 s per object** at 1536 target resolution, ~20 GiB peak VRAM, GPU measured at 72.8 % mean busy
against a 0 % idle baseline — not a CPU fallback. The `int8_convrot` quantisation runs as a **native**
kernel: `comfy-kitchen` ships a working HIP backend (`convrot_w4a4_linear`, `int8_linear`, `na3d`).

Licence surface is clean end to end. The implementation is pure PyTorch — `flexgemm.py`, the sparse 3D
convolution, imports only `torch`; no nvdiffrast, no NVIDIA-licensed component, no NATTEN anywhere.
All four model repos are MIT: `Comfy-Org/{TRELLIS.2, Pixal3D, BiRefNet, MoGe}`.

Both template arms work. Pixal3D runs alongside TRELLIS.2, sharing the VAEs and ClipVision.

## The blocker

`VaeDecodeShapeTrellis` emits **NaN vertex positions** — ~0.6 % of position floats on the TRELLIS.2
arm (1.9 % of vertices), 2.5 % on Pixal3D. Reproducible to the bit on a cold repeat, and **not the
quantisation**: bf16 weights give the same rate, and three different diffusion models produce it
through the one shared decode.

It stops the shipped template at its first postprocess node:

```
RemeshMesh → remesh.py:92 _build_centroid_tree
ValueError: data must be finite, check for nan or inf values
```

Blender also refuses the raw GLB outright (`Bad glTF: json contained NaN`).

Whether this is ROCm-specific is **not established** — no NVIDIA card here for the control, and
`--cpu-vae` cannot run this VAE. That question gates any production use of the lane.

## The working path today

Strip non-finite vertices (`../prototypes/trellis2-comfyui/glb_repair.py`), then
`../prototypes/blender_decimate.py` — the track's existing cleanup, written for this class of input.
Produces a valid, 0.00 %-NaN GLB that still reads as the source object.

Caveat: the pinholes from the ~2.5 % of dropped faces speckle every surface and defeat collapse
decimation (0.02 requested, ~0.48 achieved). Good enough to inspect and iterate on; **not a
game-ready asset**.

## Samples

`samples-2026-09-19/`, all from one 1024² input (`../prototypes/inputs/prop_crate.png`, the same
image the 2026-06-22 TripoSR/MoGe tests used), rendered in Blender 4.2 outside the producing stack:

| File | What |
|---|---|
| `trellis2_raw_000.png` | TRELLIS.2 arm, raw decode, NaN-stripped — brackets, latches, handle, lid lip all reconstructed |
| `trellis2_raw_090.png` | the unseen side, plausibly hallucinated |
| `trellis2_blender_lod_000.png` | after `blender_decimate.py`; note the speckle from the NaN pinholes |
| `pixal3d_raw_000.png` | Pixal3D arm — recognisable but lumpy, softer edges, 4× the NaN rate |
