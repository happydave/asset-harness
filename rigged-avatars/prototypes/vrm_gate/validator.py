"""Gate stage: Khronos glTF-Validator over the container, accessors and buffers.

It knows nothing of VRM — `VRMC_vrm` is an unknown extension to it — so it covers what the contract
stage does not: declared accessor bounds against the data, buffer layout, reference validity.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

# VRM_GATE_VALIDATOR points the stage at a binary kept somewhere other than vendor/.
BINARY = Path(os.environ.get("VRM_GATE_VALIDATOR")
              or Path(__file__).resolve().parent / "vendor" / "gltf_validator" / "gltf_validator")
# Raised on every VRM: this validator does not know the VRM extensions.
EXPECTED_INFO = {"UNSUPPORTED_EXTENSION"}
SEVERITY_ERROR = 0


def run(report, files):
    """Validate each file; returns False when the stage could not run at all."""
    if not BINARY.is_file():
        report.add("validator", "glTF-Validator is available", False,
                   f"{BINARY} is missing — run ./fetch_vendor.sh, or pass --no-validator to switch the stage off")
        return False
    ran = True
    for path in files:
        ran = _validate(report, Path(path)) and ran
    return ran


def _validate(report, path):
    # The validator picks its parser by file extension and refuses `.vrm`, so it is shown a `.glb` name.
    with tempfile.TemporaryDirectory() as tmp:
        alias = Path(tmp) / "asset.glb"
        alias.symlink_to(path.resolve())
        try:
            proc = subprocess.run([str(BINARY), "-o", str(alias)], capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            report.add("validator", f"glTF-Validator ran on {path.name}", False, str(e))
            return False
    try:
        result = json.loads(proc.stdout)
        issues = result["issues"]
    except (json.JSONDecodeError, KeyError):
        report.add("validator", f"glTF-Validator ran on {path.name}", False,
                   f"exit {proc.returncode}, no JSON report: {proc.stderr.strip()[:200]}")
        return False
    errors = [m for m in issues["messages"] if m["severity"] == SEVERITY_ERROR]
    codes = sorted({m["code"] for m in issues["messages"] if m["severity"] != SEVERITY_ERROR})
    other = [c for c in codes if c not in EXPECTED_INFO]
    if errors:
        detail = "; ".join(f"{m['code']} at {m.get('pointer', '?')}: {m['message']}" for m in errors[:5])
    else:
        # Warnings and infos are listed, not judged: an error is the spec's verdict, the rest is advice.
        detail = (f"validator {result.get('validatorVersion')}: 0 errors, {issues['numWarnings']} warnings, "
                  f"{issues['numInfos']} infos, {issues['numHints']} hints; expected for any VRM "
                  f"{[c for c in codes if c in EXPECTED_INFO]}, other {other}")
    report.add("validator", f"{path.name} has no glTF errors", not errors and issues["numErrors"] == 0, detail)
    return True
