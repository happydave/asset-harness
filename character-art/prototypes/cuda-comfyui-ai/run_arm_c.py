#!/usr/bin/env python3
"""WI 1616 arm C -- Qwen-Image-Edit-2511 Q3_K_M (GGUF) on an RTX 5070, sm_120.

Arm A's graph with UnetLoaderGGUF in place of UNETLoader. Everything else --
prompts, seeds, sampler, steps, CFG, shift -- is held identical so the arms
are comparable. Q3_K_M rather than int8 because the 12 GiB card fits nothing
better; that is a quantisation-depth confound, recorded, not hidden.

ORIGINAL ARM A HEADER FOLLOWS:

Graph traced from the shipped template `image_qwen_image_edit_2511_int8.json`
(Comfy-Org/workflow_templates): UNETLoader -> LoraLoaderModelOnly ->
ModelSamplingAuraFlow(3.1) -> CFGNorm, TextEncodeQwenImageEditPlus for both
conditionings, KSampler euler/simple. The template's two
FluxKontextMultiReferenceLatentMethod nodes are omitted on its own Note's
authority ("not needed if you use Comfy files"); these are Comfy files.

Sampling latent is EmptySD3LatentImage rather than the template's VAEEncode,
because the turnaround output (2600x1080) is a different shape from the input
(600x1080). At denoise 1.0 the template's VAEEncode is a size carrier only.

usage: run_arm_a.py SUBJECT MODE SEED [--no-lora]
  MODE: turnaround (2600x1080, trigger prompt) | reangle (600x1080, back view)
"""
import json
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:7123"
UNET = "qwen-image-edit-2511-Q3_K_M.gguf"
CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"
LORA = "character_turnaround_sheet_v3_qwen_image_edit_2511_000000400.safetensors"

STEPS, CFG, SHIFT = 40, 4.0, 3.1

# The LoRA's card gives this as its trigger; without it the LoRA is inert and a
# LoRA-present run is indistinguishable from a LoRA-absent one.
P_TURN = "Character turnaround sheet"
P_REANGLE = ("Turn the character around to show the back view. Same character, "
             "same body, same outfit, same colors, full body, standing.")

# Profile view at full 600x1080 -- one view, all the pixels. Discriminates
# "the model degrades the snout/tusks" from "each turnaround panel only got
# 520px to render them in".
P_PROFILE = ("Turn the character to a side profile view, facing left. Same character, "
             "same head, same face, same outfit, same colors, full body, standing.")

MODES = {
    "turnaround": (2600, 1080, P_TURN),
    "reangle": (600, 1080, P_REANGLE),
    "profile": (600, 1080, P_PROFILE),
}


def build(subject, mode, seed, use_lora):
    w, h, prompt = MODES[mode]
    g = {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": UNET}},
        "5": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "7": {"class_type": "LoadImage", "inputs": {"image": subject + ".png"}},
        "8": {"class_type": "TextEncodeQwenImageEditPlus",
              "inputs": {"clip": ["5", 0], "prompt": prompt,
                         "vae": ["6", 0], "image1": ["7", 0]}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus",
              "inputs": {"clip": ["5", 0], "prompt": "",
                         "vae": ["6", 0], "image1": ["7", 0]}},
        "10": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": w, "height": h, "batch_size": 1}},
        "12": {"class_type": "VAEDecode",
               "inputs": {"samples": ["11", 0], "vae": ["6", 0]}},
        "13": {"class_type": "SaveImage",
               "inputs": {"images": ["12", 0],
                          "filename_prefix": "wi1599/%s_%s_s%d%s" % (
                              subject, mode, seed, "" if use_lora else "_nolora")}},
    }
    # Model chain: the LoRA is the only thing the negative control removes.
    src = ["1", 0]
    if use_lora:
        g["2"] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": src, "lora_name": LORA, "strength_model": 1.0}}
        src = ["2", 0]
    g["3"] = {"class_type": "ModelSamplingAuraFlow",
              "inputs": {"model": src, "shift": SHIFT}}
    g["4"] = {"class_type": "CFGNorm",
              "inputs": {"model": ["3", 0], "strength": 1.0, "pre_cfg": False}}
    g["11"] = {"class_type": "KSampler",
               "inputs": {"model": ["4", 0], "seed": seed, "steps": STEPS, "cfg": CFG,
                          "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["8", 0], "negative": ["9", 0],
                          "latent_image": ["10", 0], "denoise": 1.0}}
    return g


def main():
    subject, mode, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
    use_lora = "--no-lora" not in sys.argv
    g = build(subject, mode, seed, use_lora)
    req = urllib.request.Request(
        HOST + "/prompt", data=json.dumps({"prompt": g}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        res = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        print("QUEUE REJECTED:", e.read().decode()[:2000]); sys.exit(1)
    pid = res.get("prompt_id")
    if not pid:
        print("QUEUE FAILED:", json.dumps(res)[:1500]); sys.exit(1)
    print("queued %s %s seed=%d lora=%s -> %s" % (subject, mode, seed, use_lora, pid))

    t0 = time.time()
    while True:
        if time.time() - t0 > 3600:
            print("TIMEOUT"); sys.exit(1)
        time.sleep(5)
        h = json.load(urllib.request.urlopen(HOST + "/history/" + pid, timeout=60))
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        outs = [im["subfolder"] + "/" + im["filename"]
                for node in h[pid].get("outputs", {}).values()
                for im in node.get("images", [])]
        print("status=%s in %.0fs  %s" % (st.get("status_str"), time.time() - t0,
                                          ",".join(outs)))
        if st.get("status_str") != "success":
            for m in st.get("messages", [])[-6:]:
                print("  ", str(m)[:400])
            sys.exit(2)
        return


if __name__ == "__main__":
    main()
