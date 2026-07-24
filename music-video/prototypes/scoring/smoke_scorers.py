#!/usr/bin/env python3
"""WI 1037: smoke-test that all four clean-licence scorers load and produce numbers on existing assets.
Validates the machine-scoring half + pre-downloads weights, independent of ai2 generation.
"""
import sys
from pathlib import Path

PROTO = Path(__file__).resolve().parents[1]
STILL = PROTO / "outputs" / "lobby" / "assets" / "shot04.png"          # existing WI 1004 still
SONG1 = PROTO / "outputs" / "clamor_hold_the_line_seed701.flac"        # existing WI 1001 song
PROMPT = ("two survivors inside a dark ruined building, one holding up a burning red flare, a menacing "
          "shadow in a broken stairwell, painterly tabletop RPG concept art, moody atmospheric")
BRIEF = "post-apocalyptic folk rock with male and female vocals, gritty clean singing, melancholic"

import torch
from PIL import Image

print("== CLIP ==")
from transformers import CLIPModel, CLIPProcessor
cm = CLIPModel.from_pretrained("openai/clip-vit-base-patch32"); cm.eval()
cp = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
inp = cp(text=[PROMPT], images=Image.open(STILL).convert("RGB"), return_tensors="pt",
         padding=True, truncation=True)
with torch.no_grad():
    o = cm(**inp)
ie = o.image_embeds / o.image_embeds.norm(dim=-1, keepdim=True)
te = o.text_embeds / o.text_embeds.norm(dim=-1, keepdim=True)
print("  CLIPScore:", round(float((ie * te).sum()), 4))

print("== PickScore ==")
from transformers import AutoModel, AutoProcessor
pp = AutoProcessor.from_pretrained("laion/CLIP-ViT-H-14-laion2B-s32B-b79K")
pm = AutoModel.from_pretrained("yuvalkirstain/PickScore_v1"); pm.eval()
inp = pp(text=[PROMPT], images=Image.open(STILL).convert("RGB"), return_tensors="pt",
         padding=True, truncation=True, max_length=77)
with torch.no_grad():
    o = pm(**inp)
    ief = o.image_embeds / o.image_embeds.norm(dim=-1, keepdim=True)
    tef = o.text_embeds / o.text_embeds.norm(dim=-1, keepdim=True)
    s1 = float((ief * tef).sum())
    o2 = pm(**inp); s2 = float(((o2.image_embeds / o2.image_embeds.norm(dim=-1, keepdim=True)) * tef).sum())
print("  PickScore:", round(s1, 4), "| deterministic:", abs(s1 - s2) < 1e-6)

print("== CLAP ==")
import soundfile as sf, librosa
from transformers import ClapModel, ClapProcessor
y, sr = sf.read(str(SONG1))
if y.ndim > 1: y = y.mean(axis=1)
if sr != 48000: y = librosa.resample(y.astype("float32"), orig_sr=sr, target_sr=48000)
clm = ClapModel.from_pretrained("laion/larger_clap_music"); clm.eval()
clp = ClapProcessor.from_pretrained("laion/larger_clap_music")
inp = clp(text=[BRIEF], audio=[y.astype("float32")], sampling_rate=48000, return_tensors="pt", padding=True)
with torch.no_grad():
    o = clm(**inp)
ae = o.audio_embeds / o.audio_embeds.norm(dim=-1, keepdim=True)
te = o.text_embeds / o.text_embeds.norm(dim=-1, keepdim=True)
print("  CLAP sim:", round(float((ae * te).sum()), 4))

print("== Audiobox Aesthetics ==")
from audiobox_aesthetics.infer import initialize_predictor
pred = initialize_predictor()
out = pred.forward([{"path": str(SONG1)}])[0]
print("  Audiobox:", {k: round(float(v), 3) for k, v in out.items()})
print("SMOKE_OK")
