#!/usr/bin/env python3
"""The finishing chain, one ComfyUI job per stage.

Order is fixed by WI 1611 and argued there — a detailer resamples a crop at `guide_size`, so it must
run where the face is big enough to repair and small enough to control:

    generate -> 2x upscale -> face detail -> hand detail -> house-style -> matte -> tokens

Run as separate jobs rather than one graph on purpose: every stage's output is then an artifact on
disk that can be inspected and diffed. That is what makes the inert-detailer check (I4) possible at
all — the check is "did these pixels change", and it needs two files. *Pixels*, not bytes: every
SaveImage output carries its own graph in a `tEXt` chunk, so two files with the same picture never
have the same bytes (WI 1732).

The house-style pass runs with **no house-style LoRA**, because none exists yet. The slot is here
and configured; what runs is the finishing checkpoint alone.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
from dataclasses import dataclass

from PIL import Image

# Checkpoints, per design-character-art.md D1: WAI generates (better race-feature legibility),
# IlustMix finishes (less cartoonish, better detail, and its weaker tusks cannot bite at low
# denoise because the tusks are already in the latent -- which scenario 7 exists to measure).
GEN_CKPT = "waiIllustriousSDXL_v170.safetensors"
FINISH_CKPT = "ilustmix_v9.safetensors"

UPSCALE_MODEL = "RealESRGAN_x4plus_anime_6B.pth"
FACE_DETECTOR = "bbox/yolov8_animeface.pt"
HAND_DETECTOR = "bbox/hand_yolov8s.pt"

NEG = ("bad quality, worst quality, worst detail, sketch, censored, blurry, lowres, "
       "jpeg artifacts, extra digits, fewer digits, bad hands, text, watermark, signature")


def _ckpt(node_id, name):
    return {node_id: {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": name}}}


def _clip_skip_2(g, node_id, src):
    g[node_id] = {"class_type": "CLIPSetLastLayer",
                  "inputs": {"clip": src, "stop_at_clip_layer": -2}}
    return [node_id, 0]


def generate(prompt: str, seed: int, prefix: str, width=768, height=1344) -> dict:
    """Stage 0 — the master. SDXL on the generation checkpoint, clip skip 2 (mandatory, fails
    silently when omitted)."""
    g = {}
    g.update(_ckpt("1", GEN_CKPT))
    clip = _clip_skip_2(g, "2", ["1", 1])
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": prompt}}
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": NEG}}
    g["5"] = {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}}
    g["6"] = {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "seed": seed, "steps": 30, "cfg": 5.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}}
    g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    g["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    return g


def upscale(image_name: str, prefix: str) -> dict:
    """A modest model upscale. RealESRGAN anime 6B is x4 by architecture, so the result is scaled
    back to 2x -- the work item asks for 2x, and feeding a detailer a 4x image wastes its
    guide_size budget."""
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALE_MODEL}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "ImageScaleBy",
              "inputs": {"image": ["3", 0], "upscale_method": "lanczos", "scale_by": 0.5}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": prefix}},
    }
    return g


def detail(image_name: str, detector: str, prompt: str, seed: int, prefix: str,
           guide_size=512, denoise=0.45) -> dict:
    """A detail pass. `bbox_detector` comes from UltralyticsDetectorProvider -- without it the
    node is silently inert, which is why I4 exists and why the driver diffs the result."""
    g = {}
    g.update(_ckpt("1", GEN_CKPT))
    clip = _clip_skip_2(g, "2", ["1", 1])
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": prompt}}
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": NEG}}
    g["5"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    g["6"] = {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": detector}}
    g["7"] = {"class_type": "FaceDetailer",
              "inputs": {"image": ["5", 0], "model": ["1", 0], "clip": clip, "vae": ["1", 2],
                         "positive": ["3", 0], "negative": ["4", 0], "bbox_detector": ["6", 0],
                         "guide_size": guide_size, "guide_size_for": True, "max_size": 1024,
                         "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "dpmpp_2m",
                         "scheduler": "karras", "denoise": denoise, "feather": 5,
                         "noise_mask": True, "force_inpaint": True, "bbox_threshold": 0.5,
                         "bbox_dilation": 10, "bbox_crop_factor": 3.0,
                         "sam_detection_hint": "center-1", "sam_dilation": 0,
                         "sam_threshold": 0.93, "sam_bbox_expansion": 0,
                         "sam_mask_hint_threshold": 0.7, "sam_mask_hint_use_negative": "False",
                         "drop_size": 10, "wildcard": "", "cycle": 1}}
    g["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    # The detector's combined mask, saved beside the image. All-zero means it found nothing, which
    # is the only way to tell a skipped pass from an inert one (WI 1611's edge case, WI 1732).
    g["9"] = {"class_type": "MaskToImage", "inputs": {"mask": ["7", 3]}}
    g["10"] = {"class_type": "SaveImage",
               "inputs": {"images": ["9", 0], "filename_prefix": prefix + MASK_SUFFIX}}
    return g


def house_style(image_name: str, prompt: str, seed: int, prefix: str, denoise: float) -> dict:
    """The coherence pass: img2img on the finishing checkpoint at low denoise.

    No house-style LoRA is loaded -- design D3 defers it (choose a style, collect and curate a
    dataset, train, iterate). What runs here is the finishing *model* alone, which is also what
    scenario 7 measures.
    """
    g = {}
    g.update(_ckpt("1", FINISH_CKPT))
    clip = _clip_skip_2(g, "2", ["1", 1])
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": prompt}}
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": NEG}}
    g["5"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    g["6"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}}
    g["7"] = {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["6", 0], "seed": seed, "steps": 30, "cfg": 5.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": denoise}}
    g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}}
    g["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}}
    return g


def matte(image_name: str, prefix: str) -> dict:
    """Background removal via ComfyUI core rather than a custom node (plan R3).

    Core 0.34.6 ships LoadBackgroundRemovalModel + RemoveBackground and WI 1600 already proved them
    on this hardware, so the chain carries one fewer custom node than the work item assumed.
    """
    # The InvertMask reconciles two nodes that disagree about what a MASK means (WI 1636).
    # `RemoveBackground` emits a *foreground* mask; `JoinImageWithAlpha` follows ComfyUI's
    # convention that a mask marks what is masked *out*, and computes `alpha = 1.0 - mask`. Wired
    # directly the two negations compose rather than cancel, and the figure becomes the hole.
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "LoadBackgroundRemovalModel",
              "inputs": {"bg_removal_name": "birefnet.safetensors"}},
        "3": {"class_type": "RemoveBackground",
              "inputs": {"bg_removal_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "InvertMask", "inputs": {"mask": ["3", 0]}},
        "5": {"class_type": "JoinImageWithAlpha",
              "inputs": {"image": ["1", 0], "alpha": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": prefix}},
    }
    return g


#: Appended to a detail stage's filename prefix for its mask output; the driver recognises the mask
#: by this suffix in the filename ComfyUI reports.
MASK_SUFFIX = "_mask"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _decode(data: bytes, what: str) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        return im
    except Exception as e:  # PIL raises several types; the caller only needs "not an image"
        raise ValueError(f"{what} is not a decodable image: {e}") from e


def is_inert(before: bytes, after: bytes) -> bool:
    """True when a stage returned its input's pixels unchanged.

    A `FaceDetailer` whose detector found nothing, or never loaded, runs, reports success and returns
    its input, so unchanged pixels are that outcome's observable (I4). Decoded pixels, not file
    bytes: ComfyUI embeds each stage's own graph in the PNG, so the bytes always differ (WI 1732).
    Mode and size are part of the comparison — an added alpha channel is a change.

    Raises ValueError when either side is not an image; a stage that produced a non-image has
    failed, and that is neither inert nor changed.
    """
    a = _decode(before, "before"); b = _decode(after, "after")
    return a.mode == b.mode and a.size == b.size and a.tobytes() == b.tobytes()


def mask_detected(data: bytes) -> bool:
    """True when the saved detector mask has any pixel above zero, i.e. the detector found something.

    The mask arrives as an RGB image (SaveImage takes images), so the first channel is read.
    """
    im = _decode(data, "mask")
    lo, hi = im.getchannel(0).getextrema()
    return hi > 0


@dataclass(frozen=True)
class Verdict:
    outcome: str   # "pass" | "skip" | "fail"
    reason: str


def detail_verdict(detected: bool, pixels_changed: bool) -> Verdict:
    """Decide a detail stage from what its detector found and what its pixels did. Pure.

    Four cells, three outcomes. A detector that finds nothing (the anime detector on a dragonborn's
    head) is a skip: recorded, not fatal. Found-but-unchanged is the inert detector (I4);
    changed-but-nothing-found is not a detail pass at all.
    """
    if detected and pixels_changed:
        return Verdict("pass", "detector found a region and the pass changed it")
    if not detected and not pixels_changed:
        return Verdict("skip", "detector found nothing; pass skipped, image carried forward unchanged")
    if detected and not pixels_changed:
        return Verdict("fail", "detector found a region but the output is pixel-identical to the "
                               "input -- the detail pass was inert (I4)")
    return Verdict("fail", "detector found nothing yet the pixels changed -- the stage did "
                           "something other than the detail pass it was asked for")


def embedded_recipe(data: bytes) -> dict | None:
    """The seed and positive prompt a ComfyUI PNG says it was made with, from its `prompt` chunk.

    Returns None when the chunk is absent (a ComfyUI started with `--disable-metadata`) or carries
    no KSampler; a caller treats that as "provenance absent", not as a mismatch. The positive
    prompt is the text of the CLIPTextEncode the KSampler's `positive` input points at.
    """
    chunk = _png_text(data, "prompt")
    if chunk is None:
        return None
    try:
        graph = json.loads(chunk)
    except ValueError:
        return None
    for node in graph.values():
        if not isinstance(node, dict) or node.get("class_type") != "KSampler":
            continue
        inputs = node.get("inputs", {})
        pos = inputs.get("positive")
        text = None
        if isinstance(pos, list) and pos and str(pos[0]) in graph:
            text = graph[str(pos[0])].get("inputs", {}).get("text")
        return {"seed": inputs.get("seed"), "prompt": text}
    return None


def _png_text(data: bytes, key: str) -> str | None:
    """The value of the first `tEXt` chunk with `key`, or None. Walks chunks; no decoding."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i = 8
    while i + 8 <= len(data):
        n, = struct.unpack(">I", data[i:i + 4])
        kind = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + n]
        if kind == b"tEXt":
            k, _, v = body.partition(b"\x00")
            if k.decode("latin-1") == key:
                return v.decode("latin-1")
        i += 12 + n
    return None


def figure_is_opaque(data: bytes, *, border_frac: float = 0.02,
                     min_transparent: float = 0.02) -> bool:
    """True when `data` decodes to a cut-out with the figure opaque and the background not.

    Matting is the one stage whose failure no other check can see: an inverted alpha is still the
    right size, the right format and borderless, so size, format and border assertions all pass on
    a token that is a character-shaped hole (WI 1636).

    Pure -- it decodes bytes and returns a verdict, never writing, so a test can hand it a real
    inverted artifact.

    Both degenerate directions are refused. No transparency at all means background removal
    produced nothing usable, which is the inert-detailer failure (I4) in another stage.

    Assumes the subject does not reach the frame edge, so a cut-out's border is mostly transparent
    and its middle mostly not. A full-bleed subject is refused; `explain_alpha` reports the
    fractions it measured.
    """
    border, interior, transparent = _alpha_stats(data)
    if border is None:
        return False
    return transparent >= min_transparent and border < 0.5 and interior > 0.5


def explain_alpha(data: bytes) -> str:
    """What `figure_is_opaque` saw, for a failure message that can be acted on."""
    border, interior, transparent = _alpha_stats(data)
    if border is None:
        return "image has no alpha channel"
    return (f"border opaque {border:.1%} (want <50%), interior opaque {interior:.1%} (want >50%), "
            f"fully transparent {transparent:.1%} (want >=2%); assumes the subject does not reach "
            f"the frame edge")


def _alpha_stats(data: bytes):
    """(border opaque fraction, interior opaque fraction, fully-transparent fraction).

    Returns (None, None, None) for an image with no alpha rather than raising, so a caller's
    failure message is about the matte instead of about a traceback.
    """
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if "A" not in img.getbands():
        return None, None, None
    a = img.getchannel("A")

    w, h = a.size
    inset = max(1, round(min(w, h) * 0.02))
    edge = [a.getpixel((x, y))
            for x in range(0, w, max(1, w // 64))
            for y in (0, inset, h - 1 - inset, h - 1)]
    mid = a.crop((w // 4, h // 4, w - w // 4, h - h // 4))
    mid = mid.resize((max(1, mid.width // 8), max(1, mid.height // 8)))
    mid_px = list(mid.getdata())

    hist = a.histogram()
    total = sum(hist)
    return (sum(1 for v in edge if v > 127) / len(edge),
            sum(1 for v in mid_px if v > 127) / len(mid_px),
            hist[0] / total)
