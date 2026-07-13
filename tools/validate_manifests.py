"""Manifest validation gate for asset-harness (plain python3, no third-party imports).

Run from the repo root:  python3 tools/validate_manifests.py

This IS the CI gate under this repo's convention (plain-python check scripts, cf.
2d/prototypes/test_build_atlas.py): run it before committing any change that touches a
sidecar manifest or contracts/. It performs two checks and exits nonzero on any failure:

1. PIN check — every file in contracts/ matches the SHA-256 recorded in contracts/PIN.
   Drift means the vendored copy was edited by hand or a contracts update was applied
   without re-vendoring; fix by re-running asset-studio's vendor_to_harness.py.
2. Schema validation — each known sidecar manifest validates against
   #/definitions/sidecarManifest of the vendored contracts schema.

The contracts source of truth lives in the asset-studio repo
(packages/contracts/); this directory is a pinned vendored copy.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

MANIFESTS = [
    "rigged-avatars/prototypes/out/robot_manifest.json",
    "rigged-avatars/prototypes/out/corn_manifest.json",
    "rigged-avatars/prototypes/out/popcorn_burst_manifest.json",
    "mechanical-kit/parts/manifest.json",
]


def check_pin():
    failures = []
    pin = json.loads((CONTRACTS / "PIN").read_text())
    for name, expected in pin["files"].items():
        path = CONTRACTS / name
        if not path.exists():
            failures.append("PIN: vendored file missing: %s" % name)
            continue
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            failures.append("PIN: %s drifted from pinned hash (re-vendor from asset-studio)" % name)
    return pin, failures


def check_manifests():
    sys.path.insert(0, str(CONTRACTS))
    import contracts_validator  # vendored, stdlib-only

    schema = json.loads((CONTRACTS / "contracts-1.schema.json").read_text())
    failures = []
    for rel in MANIFESTS:
        path = ROOT / rel
        if not path.exists():
            failures.append("%s: file missing" % rel)
            continue
        try:
            doc = json.loads(path.read_text())
        except ValueError as e:
            failures.append("%s: JSON parse error: %s" % (rel, e))
            continue
        errors = contracts_validator.validate_ref(
            schema, "#/definitions/sidecarManifest", doc)
        for err in errors:
            failures.append("%s: %s" % (rel, err))
    return failures


def main():
    pin, failures = check_pin()
    if not failures:
        print("PIN ok (contracts %s, schema_version %s)"
              % (pin["contracts_version"], pin["schema_version"]))
        manifest_failures = check_manifests()
        for rel in MANIFESTS:
            if not any(f.startswith(rel) for f in manifest_failures):
                print("ok   %s" % rel)
        failures.extend(manifest_failures)
    for f in failures:
        print("FAIL %s" % f)
    print("%d failure(s)" % len(failures) if failures else "all manifests valid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
