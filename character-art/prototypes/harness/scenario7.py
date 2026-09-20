#!/usr/bin/env python3
"""Scenario 7 / design owner-gate 1: does the house-style pass erode small features?

design-character-art.md D1 nominates IlustMix as the finishing model on the argument that its
measured weakness -- it renders smaller half-orc tusks than WAI -- "cannot bite at denoise
0.20-0.30 because the tusks are already fixed in the latent". The design review (F5) called that
plausible and unmeasured. This measures it.

Same input image, only denoise varies, so the comparison is clean.
"""
from pathlib import Path
import chain, comfy_client as cc

SERVER = "http://127.0.0.1:7124"
SRC = "halforc_hand.png"          # the stage the house-style pass consumes
PROMPT = ("masterpiece, best quality, 1boy, half-orc, green skin, tusks, protruding lower canines, "
          "heavy brow, muscular, black braided hair, fur and leather armor, fantasy adventurer")
out = Path.home()/"wi1611"/"scenario7"; out.mkdir(parents=True, exist_ok=True)

for dn in (0.20, 0.30):
    g = chain.house_style(SRC, PROMPT, 202, f"wi1611/s7_{int(dn*100)}", dn)
    pid = cc.queue(SERVER, g)
    hist = cc.wait_for_history(SERVER, pid, label=f"denoise{dn}")
    got = cc.download_outputs(SERVER, hist, out/f"halforc_denoise{int(dn*100)}", kinds=("images",))
    print(f"denoise {dn}: {got}")
