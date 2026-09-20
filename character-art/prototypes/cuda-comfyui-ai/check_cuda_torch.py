"""Build-time half of WI 1600's check_torch.py, inverted for CUDA.

ComfyUI's requirements.txt lists torch/torchvision/torchaudio UNPINNED, so the
pip layer can silently replace the base's cu128 build with a wheel that lacks
sm_120 — which on this card degrades to "no usable GPU" rather than an error.

Only the version and CUDA build are checkable here: `torch.cuda.get_arch_list()`
returns [] with no GPU attached, and `podman build` has none. The sm_120
assertion therefore lives in check_sm120.py, run at container start.
"""
import json, torch
base = json.load(open("/opt/torch-base.json"))
print("base:", base, "now:", torch.__version__, torch.version.cuda)
assert torch.version.cuda, "CUDA torch was replaced by a CPU build"
if torch.__version__ != base["v"]:
    raise SystemExit("torch changed: %s -> %s" % (base["v"], torch.__version__))
print("OK: cu128 torch intact (sm_120 verified at container start)")
