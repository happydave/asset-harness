#!/usr/bin/env python3
"""Write a contracts schema_version 3 `rigged-avatar` sidecar for an exported avatar.

    python3 write_avatar_sidecar.py NAME_DIR/NAME.vrm [--id ID]

Reads `<name>_evidence.json` and `<name>_manifest.json` beside the VRM (the generator writes both),
the humanoid table in vrm_export.py and the archetype tables in arkit52.py, and writes
`<name>_sidecar.json` beside them. The evidence is the source: nothing here re-declares a table.
Refuses without the evidence, because a sidecar invented from the manifest alone would describe
nothing checkable. Stdlib only (WI 1368).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arkit52  # noqa: E402

SCHEMA_VERSION = 3

# vrm_export.HUMANOID_19_EYES as the VRM 1.0 file spells the slots (camelCase); copied, because
# vrm_export imports bpy at module level. Change both together.
HUMANOID_19_EYES = {
    "hips": "hips", "spine": "spine", "chest": "chest", "neck": "neck", "head": "head",
    "shoulder.L": "leftShoulder", "upper_arm.L": "leftUpperArm", "forearm.L": "leftLowerArm", "hand.L": "leftHand",
    "shoulder.R": "rightShoulder", "upper_arm.R": "rightUpperArm", "forearm.R": "rightLowerArm", "hand.R": "rightHand",
    "thigh.L": "leftUpperLeg", "shin.L": "leftLowerLeg", "foot.L": "leftFoot",
    "thigh.R": "rightUpperLeg", "shin.R": "rightLowerLeg", "foot.R": "rightFoot",
    "eye.L": "leftEye", "eye.R": "rightEye",
}

AUTHORED_LANE = {
    "status": "clean",
    "commercial_in_game": True,
    "standalone_redistributable": True,
    "source": {"kind": "authored"},
}


def build(vrm: Path, entry_id: str | None) -> dict:
    stem = vrm.name.split(".")[0]
    evidence_path = vrm.with_name(f"{stem}_evidence.json")
    manifest_path = vrm.with_name(f"{stem}_manifest.json")
    if not evidence_path.is_file():
        raise SystemExit(f"refusing: no evidence beside the file ({evidence_path})")
    evidence = json.loads(evidence_path.read_text())
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}

    archetype = manifest.get("head_variant") or "stylized-v1"
    authored = list(evidence["morphs"]["authored"])
    stubs = {reason: list(names) for reason, names in evidence["morphs"]["stub_reasons"].items()}
    springs_ev = evidence["springs"]
    gaze_ev = evidence["gaze"]
    bones = sorted(set(HUMANOID_19_EYES) | {j for ch in springs_ev["chains"] for j in ch["joints"]}
                   | {c["bone"] for c in springs_ev["colliders"]})
    slot_by_bone = HUMANOID_19_EYES
    gaze_slots = [slot_by_bone[b] for b in gaze_ev["bones"]]

    entry = {
        "schema_version": SCHEMA_VERSION,
        "id": entry_id or stem.replace("_", "-"),
        "class": "rigged-avatar",
        "frame": "authored Z-up; exported +Y up, metres; VRM 1.0 faces +Z",
        "license_record": dict(AUTHORED_LANE, text=manifest.get("license", "")),
        "provenance": {"source_of_truth": "manual-import",
                       "generator_script": manifest.get("generator_script", evidence.get("generator_script", ""))},
        "asset": manifest.get("asset", ""),
        "bind": manifest.get("bind", ""),
        "head_variant": archetype,
        "generator_script": manifest.get("generator_script", ""),
        "bones": bones,
        "humanoid": {b: slot_by_bone[b] for b in sorted(HUMANOID_19_EYES)},
        "expressions": {
            "vocabulary": "arkit-52",
            "declared": list(arkit52.ARKIT_52),
            "authored": authored,
            "stubs": stubs,
            "nominal_mm": {n: arkit52.NOMINAL_MM[n] for n in authored if n in arkit52.NOMINAL_MM},
        },
        "presets": {
            "composed": {p: [{"shape": s, "weight": w} for s, w in arkit52.PRESET_COMPOSITION[p]]
                         for p in evidence["presets"]["morph_composed"]},
            "empty_by_design": list(evidence["presets"]["empty_by_design"]),
            "overrides": {p: dict(o) for p, o in evidence["presets"]["overrides"].items()},
        },
        "gaze": {"mode": gaze_ev["mode"], "bones": list(gaze_ev["bones"]), "humanoid_slots": gaze_slots},
        "springs": {
            "colliders": [{"name": c["name"], "bone": c["bone"], "center": list(c["center"]), "radius": c["radius"]}
                          for c in springs_ev["colliders"]],
            "collider_groups": {g: list(m) for g, m in springs_ev["collider_groups"].items()},
            "chains": [{k: ch[k] for k in ("name", "joints", "center", "collider_groups",
                                           "hit_radius", "stiffness", "gravity_power", "drag_force") if k in ch}
                       for ch in springs_ev["chains"]],
        },
        "artifacts": {k: Path(v).name for k, v in evidence.get("artifacts", {}).items()
                      if k in ("vrm1", "vrm0", "glb") and isinstance(v, str)},
    }
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vrm", type=Path)
    ap.add_argument("--id")
    args = ap.parse_args(argv)
    problems = arkit52.check_contract()
    if problems:
        raise SystemExit("the contract table is inconsistent:\n  " + "\n  ".join(problems))
    entry = build(args.vrm, args.id)
    out = args.vrm.with_name(f"{args.vrm.name.split('.')[0]}_sidecar.json")
    out.write_text(json.dumps(entry, indent=2) + "\n")
    print(f"wrote {out}: {len(entry['bones'])} bones, {len(entry['expressions']['authored'])} authored, "
          f"{sum(len(v) for v in entry['expressions']['stubs'].values())} stubs, "
          f"{len(entry['presets']['composed'])} composed presets, {len(entry['springs']['chains'])} chains")
    return 0


if __name__ == "__main__":
    sys.exit(main())
