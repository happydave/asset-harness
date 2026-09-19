import json, torch
base = json.load(open("/opt/torch-base.json"))
print("base:", base, "now:", torch.__version__, torch.version.hip)
assert torch.version.hip, "torch.version.hip empty - ROCm torch was replaced by the ComfyUI layer"
if torch.__version__ != base["v"]:
    raise SystemExit(f"torch version changed by the ComfyUI layer: {base['v']} -> {torch.__version__}")
print("OK: ROCm torch intact")
