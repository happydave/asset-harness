# ComfyUI on CUDA, on `ai`'s RTX 5070 — the estate's only NVIDIA container lane

Scaffolding from the WI 1616 spike (WI 1599's arm C). Full evidence and verdict:
`tickets/docs/pending/1616-ah-spike-arm-c-cuda-comfyui-4bit-qwen-edit/spike.md`.

Two results: **a CUDA ComfyUI container works on `ai`**, and **4-bit (Q3_K_M) preserves non-human
race features except the smallest one** — the half-orc's tusks degraded where a dragonborn's snout
did not.

Nothing here is production code.

## The blocker you will hit first: podman 4.9.3 cannot use the CDI specs

`nvidia-container-toolkit` is installed on `ai` and `/etc/cdi/nvidia.yaml` exists, but
`podman run --device nvidia.com/gpu=all` fails with `unresolvable CDI devices`. Two reasons, both
confirmed with `podman --log-level=debug`:

1. podman 4.9.3's CDI library rejects the nvidia-ctk 0.7.0 spec on the unknown field
   **`additionalGids`**;
2. it **ignores `cdi_spec_dirs`**, so there is no user-level override.

**Workaround, no root needed:**

```
ARGS=$(python3 cdi_to_podman_args.py all)
podman run --rm $ARGS <image> sh -c 'ldconfig 2>/dev/null; <command>'
```

`cdi_to_podman_args.py` derives `--device`/`-v`/`-e` flags from the world-readable spec.
**`ldconfig` at container start is not optional** — it replaces the spec's `update-ldcache` hook by
recreating the SONAME symlinks (`libnvidia-ml.so.1` → `libnvidia-ml.so.580.173.02`). Without it the
container starts, the devices are present, and every NVIDIA library is invisible.

Safe on this host because `/dev/nvidia*` are mode **666**, so the spec's `additionalGids` (44, 992)
buy nothing — worth knowing, because `notdave` on `ai` is in no supplementary groups at all.

Root-side alternative, not taken: strip `additionalGids` and set `cdiVersion: 0.6.0` in
`/etc/cdi/nvidia.yaml` and `/var/run/cdi/nvidia.yaml`. A podman ≥ 5.0 fixes it properly.

## The image

Base pinned by digest:
`docker.io/pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385`
(torch **2.8.0+cu128**, cudnn9). The host's CUDA is 12.4, which *predates* this card's sm_120 —
the container's cu128 torch is what makes the GPU usable, so do not unpin it.

```
podman build -t localhost/wi1616-comfyui-cuda:0.34.6 -f Containerfile .
```

Two assertions, and the split matters: `check_cuda_torch.py` runs at **build** time and checks only
what is observable there (torch version and CUDA build unchanged, catching ComfyUI's unpinned
`torch` line pulling a wheel without sm_120). `check_sm120.py` runs at **container start**, with the
GPU attached, because `torch.cuda.get_arch_list()` returns `[]` with no GPU and a build-time sm_120
assertion fails on a perfectly healthy image.

## Models and the VRAM ceiling

`fetch.sh` gets Q3_K_M + the fp8 text encoder + VAE + the turnaround LoRA (all apache-2.0).

**The 12,227 MiB card is the binding constraint.** Nothing better than Q3_K_M fits:

| Candidate | Size | Verdict |
|---|---|---|
| Nunchaku 2511 balance_fp4 | 12,475 MiB | does not fit |
| GGUF Q4_K_M | 12,631 MiB | does not fit |
| Nunchaku 2511 balance_int4 | 12,068 MiB | 159 MiB spare — unusable |
| **GGUF Q3_K_M** | 9,461 MiB | **fits** |

**`--lowvram` is required.** Without it, a 600×1080 generation OOMs at `KSampler`: the 8.9 GiB text
encoder and 9.4 GiB UNet cannot co-reside on a card also driving a desktop. With it: 340 s per
600×1080 image, peak 11,397 MiB.

**A 2600×1080 five-view turnaround sheet is not possible on this card at all.** Single views here;
sheets on `ai2` (see `qwen-edit-2511/`).

Untried and the obvious first tuning move: the `nvfp4` text encoder (5,831 MiB, Blackwell-native)
in place of the 8,949 MiB fp8 one.

## Cost against the AMD lane

340 s at 600×1080 here, against **160 s** for the identical image on `ai2`'s R9700. ~2× slower
**because of `--lowvram`**, not because of the vendor.
