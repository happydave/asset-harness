#!/usr/bin/env python3
"""ComfyUI API graphs for the four group-shot routes.

One graph per job rather than one graph per route, for the reason WI 1611 gives: every stage's
output is then a file on disk that can be inspected and diffed, which is what makes a control
possible at all.

Settings are held identical across routes -- same checkpoint, sampler, scheduler, steps, CFG and
clip skip -- so a difference between two routes' output is a difference between the routes. The
one exception is denoise, which is the parameter under test wherever it varies.
"""
from __future__ import annotations

import scene

CKPT = "ilustmix_v9.safetensors"          # design D7, the house style
CONTROLNET = "controlnet-union-sdxl-1.0-promax.safetensors"
UPSCALE_MODEL = "RealESRGAN_x4plus_anime_6B.pth"

STEPS, CFG = 30, 5.0
SAMPLER, SCHEDULER = "dpmpp_2m", "karras"


def _base(g: dict) -> list:
    """Checkpoint + clip skip 2. `CLIPSetLastLayer -2` is mandatory on Illustrious and fails
    silently when omitted (WI 1611)."""
    g["ckpt"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}}
    g["clip"] = {"class_type": "CLIPSetLastLayer",
                 "inputs": {"clip": ["ckpt", 1], "stop_at_clip_layer": -2}}
    return ["clip", 0]


def _text(g: dict, node: str, clip, text: str):
    g[node] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip, "text": text}}
    return [node, 0]


def _sample(g: dict, node: str, pos, neg, latent, seed: int, denoise: float = 1.0,
            model=("ckpt", 0)):
    g[node] = {"class_type": "KSampler",
               "inputs": {"model": list(model), "positive": pos, "negative": neg,
                          "latent_image": latent, "seed": seed, "steps": STEPS, "cfg": CFG,
                          "sampler_name": SAMPLER, "scheduler": SCHEDULER, "denoise": denoise}}
    return [node, 0]


def _decode_save(g: dict, samples, prefix: str):
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": samples, "vae": ["ckpt", 2]}}
    g["save"] = {"class_type": "SaveImage",
                 "inputs": {"images": ["dec", 0], "filename_prefix": prefix}}
    return g


# --------------------------------------------------------------------------- route 1


def route1_direct(seed: int, prefix: str) -> dict:
    """Everyone in one prompt, layout uncontrolled. The tag lane unaided."""
    g = {}
    clip = _base(g)
    pos = _text(g, "pos", clip, scene.scene_prompt())
    neg = _text(g, "neg", clip, scene.NEG)
    g["lat"] = {"class_type": "EmptyLatentImage",
                "inputs": {"width": scene.GEN_W, "height": scene.GEN_H, "batch_size": 1}}
    return _decode_save(g, _sample(g, "ks", pos, neg, ["lat", 0], seed), prefix)


# --------------------------------------------------------------------------- route 4


def route4_regional(seed: int, prefix: str, collapse: bool = False) -> dict:
    """Layout in the graph instead of in the prompt.

    A global conditioning carries the setting; each character gets its own encode bound to its own
    slice of the canvas. Each region's text stays inside the 77-token CLIP budget on its own, which
    the single concatenated prompt of route 1 cannot.

    `collapse=True` is spike.md's FC1 control: every region is widened to the full frame, so the
    mechanism carries no spatial information while everything else -- seed, prompts, strengths,
    node count -- is unchanged. If the layout survives that, the layout was never being controlled.
    """
    g = {}
    clip = _base(g)
    neg = _text(g, "neg", clip, scene.NEG)

    parts = [_text(g, "base", clip, scene.base_prompt())]
    for i, f in enumerate(scene.CAST):
        c = _text(g, f"r{i}", clip, scene.region_prompt(f))
        x, w = (0.0, 1.0) if collapse else (f.x0, f.x1 - f.x0)
        g[f"a{i}"] = {"class_type": "ConditioningSetAreaPercentage",
                      "inputs": {"conditioning": c, "width": w, "height": 1.0,
                                 "x": x, "y": 0.0, "strength": 1.0}}
        parts.append([f"a{i}", 0])

    acc = parts[0]
    for i, p in enumerate(parts[1:]):
        g[f"cmb{i}"] = {"class_type": "ConditioningCombine",
                        "inputs": {"conditioning_1": acc, "conditioning_2": p}}
        acc = [f"cmb{i}", 0]

    g["lat"] = {"class_type": "EmptyLatentImage",
                "inputs": {"width": scene.GEN_W, "height": scene.GEN_H, "batch_size": 1}}
    return _decode_save(g, _sample(g, "ks", acc, neg, ["lat", 0], seed), prefix)


# --------------------------------------------------------------------------- route 3


def route3_posed(seed: int, prefix: str, scaffold_image: str, strength: float = 0.85) -> dict:
    """A drawn OpenPose scaffold places the figures; the prompt says who they are.

    `strength=0.0` is spike.md's FC1 control for this route -- the scaffold is still loaded and
    still passed through the same nodes, so only its influence is removed.
    """
    g = {}
    clip = _base(g)
    pos = _text(g, "pos", clip, scene.scene_prompt())
    neg = _text(g, "neg", clip, scene.NEG)

    g["cn"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": CONTROLNET}}
    g["cnt"] = {"class_type": "SetUnionControlNetType",
                "inputs": {"control_net": ["cn", 0], "type": "openpose"}}
    g["hint"] = {"class_type": "LoadImage", "inputs": {"image": scaffold_image}}
    g["app"] = {"class_type": "ControlNetApplyAdvanced",
                "inputs": {"positive": pos, "negative": neg, "control_net": ["cnt", 0],
                           "image": ["hint", 0], "strength": strength,
                           "start_percent": 0.0, "end_percent": 0.85}}

    g["lat"] = {"class_type": "EmptyLatentImage",
                "inputs": {"width": scene.GEN_W, "height": scene.GEN_H, "batch_size": 1}}
    return _decode_save(g, _sample(g, "ks", ["app", 0], ["app", 1], ["lat", 0], seed), prefix)


def region_inpaint(seed: int, prefix: str, image: str, mask_image: str, text: str,
                   denoise: float) -> dict:
    """Route 3's second half: re-render one figure's region over pixels pasted from its master.

    The master's own pixels are already in the region, so the sampler is correcting lighting and
    edges rather than inventing a character -- which is why this can run at low denoise, and why
    denoise is the parameter that decides whether identity survives.
    """
    g = {}
    clip = _base(g)
    pos = _text(g, "pos", clip, text)
    neg = _text(g, "neg", clip, scene.NEG)
    g["img"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    g["msk"] = {"class_type": "LoadImageMask", "inputs": {"image": mask_image, "channel": "red"}}
    g["enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["img", 0], "vae": ["ckpt", 2]}}
    g["nm"] = {"class_type": "SetLatentNoiseMask",
               "inputs": {"samples": ["enc", 0], "mask": ["msk", 0]}}
    return _decode_save(g, _sample(g, "ks", pos, neg, ["nm", 0], seed, denoise), prefix)


# --------------------------------------------------------------------------- route 2


def backdrop(seed: int, prefix: str) -> dict:
    """Route 2's environment plate. Generated on the same checkpoint as the figures: a composite is
    tested hardest when a style mismatch cannot be blamed for a failure of integration."""
    g = {}
    clip = _base(g)
    pos = _text(g, "pos", clip, scene.backdrop_prompt())
    neg = _text(g, "neg", clip, scene.NEG + ", people, person, character, figure")
    g["lat"] = {"class_type": "EmptyLatentImage",
                "inputs": {"width": scene.GEN_W, "height": scene.GEN_H, "batch_size": 1}}
    return _decode_save(g, _sample(g, "ks", pos, neg, ["lat", 0], seed), prefix)


def unify(seed: int, prefix: str, image: str, denoise: float) -> dict:
    """The low-denoise pass that is supposed to make a paste-up read as one scene.

    This is the same operation as the finishing chain's house-style pass, so WI 1611 scenario 7's
    measurement applies to it: at denoise 0.20 and 0.30 the half-orc's tusks were unchanged in size
    and position. Identity risk here is therefore bounded by a measurement rather than a guess.
    """
    g = {}
    clip = _base(g)
    pos = _text(g, "pos", clip, scene.scene_prompt())
    neg = _text(g, "neg", clip, scene.NEG)
    g["img"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    g["enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["img", 0], "vae": ["ckpt", 2]}}
    return _decode_save(g, _sample(g, "ks", pos, neg, ["enc", 0], seed, denoise), prefix)


# --------------------------------------------------------------------------- shared


def upscale_2x(image: str, prefix: str) -> dict:
    """Every route is scored at 2x its generation size. RealESRGAN anime 6B is x4 by architecture,
    so the result is scaled back -- feeding the scorer a 4x image would not add information."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALE_MODEL}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "ImageScale",
              "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                         "width": scene.SCORE_W, "height": scene.SCORE_H, "crop": "disabled"}},
        "5": {"class_type": "SaveImage",
              "inputs": {"images": ["4", 0], "filename_prefix": prefix}},
    }
