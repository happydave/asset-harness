#!/usr/bin/env python3
"""WI 1599 — generate candidate source portraits for the edit-model spike.

Queues SDXL txt2img jobs against the shared ComfyUI on 127.0.0.1:8188 (read/queue
only; the service is not modified). Four subjects, three seeds each.

The source for a turnaround sheet must be a FULL-BODY figure at the LoRA's
600x1080 input aspect, not a head-and-shoulders portrait. Generated at an SDXL
bucket and cropped (never squeezed) to 0.5556 -- a horizontal squeeze in the
input would compound the narrowing the LoRA's author reports in 2511 output.
"""
import json
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
CKPT = "waiIllustriousSDXL_v170.safetensors"

# SDXL bucket nearest the LoRA's 600x1080 (0.5556); cropped to exact aspect later.
W, H = 768, 1344

COMMON = (
    "masterpiece, best quality, amazing quality, very aesthetic, absurdres, "
    "solo, full body, standing, facing viewer, looking at viewer, "
    "arms at sides, relaxed pose, full body visible, feet visible, "
    "simple background, white background, even lighting, "
    "dungeons and dragons character, fantasy character concept art"
)

NEG = (
    "bad quality, worst quality, worst detail, sketch, censored, blurry, lowres, "
    "jpeg artifacts, multiple views, multiple girls, multiple boys, 2boys, 2girls, "
    "cropped, out of frame, cut off, head out of frame, text, watermark, signature, "
    "weapon, holding weapon, cape, cloak, long coat"
)

SUBJECTS = {
    # Horns and tail: the tail is the feature most easily lost in a re-angle.
    "tiefling": (
        "1girl, tiefling, red skin, long curved horns, large demon horns, "
        "demon tail, long tail, pointed ears, yellow eyes, white hair, long hair, "
        "brown leather armor, fantasy adventurer outfit, " + COMMON
    ),
    # The hardest case: a non-human head shape with no human nose or lips.
    "dragonborn": (
        "1other, dragonborn, draconic humanoid, dragon head, reptile head, "
        "long snout, muzzle, bronze scales, scaled skin, horns, frills, "
        "reptilian eyes, no human nose, muscular, steel plate armor, "
        "fantasy adventurer, " + COMMON
    ),
    # The subtle case: tusks are small, and a pipeline that holds horns may still file them down.
    "halforc": (
        "1boy, half-orc, green skin, tusks, protruding lower canines, "
        "large jaw, heavy brow, muscular, black braided hair, "
        "fur and leather armor, fantasy adventurer, " + COMMON
    ),
    # Control: must have NO non-human features, and must re-project cleanly.
    "human": (
        "1boy, human, tan skin, short brown hair, short beard, brown eyes, "
        "brown leather armor, fantasy adventurer, " + COMMON
    ),
}

SEEDS = [101, 202, 303]


def graph(prompt, seed, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPSetLastLayer",
              "inputs": {"clip": ["1", 1], "stop_at_clip_layer": -2}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": prompt}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": NEG}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": W, "height": H, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "seed": seed, "steps": 30, "cfg": 5.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }


def post(path, payload):
    req = urllib.request.Request(
        HOST + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def get(path):
    with urllib.request.urlopen(HOST + path, timeout=60) as r:
        return json.load(r)


def main():
    ids = []
    for name, prompt in SUBJECTS.items():
        for seed in SEEDS:
            prefix = "wi1599/cand_%s_s%d" % (name, seed)
            res = post("/prompt", {"prompt": graph(prompt, seed, prefix)})
            if "prompt_id" not in res:
                print("QUEUE FAILED", name, seed, json.dumps(res)[:800])
                sys.exit(1)
            ids.append((name, seed, res["prompt_id"]))
            print("queued %-11s seed %-4d %s" % (name, seed, res["prompt_id"]))

    print("\n%d jobs queued; waiting..." % len(ids))
    done, t0 = set(), time.time()
    while len(done) < len(ids):
        if time.time() - t0 > 1800:
            print("TIMEOUT"); sys.exit(1)
        time.sleep(5)
        for name, seed, pid in ids:
            if pid in done:
                continue
            h = get("/history/" + pid)
            if pid in h:
                st = h[pid].get("status", {})
                outs = []
                for node in h[pid].get("outputs", {}).values():
                    for im in node.get("images", []):
                        outs.append(im["subfolder"] + "/" + im["filename"])
                print("done %-11s seed %-4d %-9s %s" % (
                    name, seed, st.get("status_str", "?"), ",".join(outs)))
                done.add(pid)
    print("\nall %d complete in %.0fs" % (len(ids), time.time() - t0))


if __name__ == "__main__":
    main()
