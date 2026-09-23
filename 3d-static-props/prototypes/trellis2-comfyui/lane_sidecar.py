#!/usr/bin/env python3
"""Write the licence sidecar for one asset the TRELLIS.2 lane produced (asset-harness WI 1749).

    python3 lane_sidecar.py GLB API_GRAPH --models DIR --checkout DIR [--out PATH]
                            [--custom-nodes a,b] [--licences lane_licences.json] [--contracts DIR]

Writes `<GLB>.lane.json`: the asset's name, size and sha256, the lane and arm, and a
`license_record` and `provenance` that validate against the contracts schema's own `licenseRecord`
and `provenance` definitions. Every model file the API graph loads must have a row in
lane_licences.json. A graph loading an unrecorded file, or more than one generator, is refused
(exit 2) and nothing is written; a record that fails the schema exits 1 and nothing is written.
The custom nodes recorded are those named by --custom-nodes, or by default every one of
CUSTOM_NODES present in the checkout, which is right only when the sidecar is written straight
after the run.
Stdlib only, plus the vendored contracts validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACTS = HERE.parents[2] / "contracts"
MODEL_SUFFIXES = (".safetensors", ".pth", ".pt", ".ckpt", ".gguf", ".bin")
CUSTOM_NODES = ("rocm_gemm_guard", "rocm_unwrap_guard", "mem_probe")
SALT = "trellis2-comfyui-lane-sidecar/1"
LANE = "trellis2-comfyui"


class Refused(Exception):
    """The graph cannot be given a sidecar; the message says why."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def model_refs(graph: dict) -> list:
    """(node id, class type, file name) for every literal input naming a model file."""
    refs = []
    for nid, node in graph.items():
        for value in node.get("inputs", {}).values():
            if isinstance(value, str) and value.endswith(MODEL_SUFFIXES):
                refs.append((nid, node["class_type"], value))
    return refs


def resolve(models: Path, name: str) -> Path:
    hits = sorted(p for p in models.rglob(name) if p.is_file())
    if len(hits) != 1:
        raise Refused(f"model file {name}: {len(hits)} matches under {models}")
    return hits[0]


def components_for(graph: dict, models: Path, table: dict) -> list:
    """The licence row and resolved path of each model file the graph loads."""
    rows = {c["file"]: c for c in table["components"]}
    found, unknown = [], []
    for _nid, _cls, name in model_refs(graph):
        path = resolve(models, name)
        rel = path.relative_to(models).as_posix()
        if rel not in rows:
            unknown.append(rel)
        elif rel not in [r["file"] for r, _ in found]:
            found.append((rows[rel], path))
    if unknown:
        raise Refused("no licence row for: " + ", ".join(sorted(set(unknown))))
    generators = sorted({r["generator"] for r, _ in found if "generator" in r})
    if len(generators) != 1:
        raise Refused(f"expected one generator in the graph, found {generators or 'none'}")
    return found


def checkout_version(checkout: Path) -> str:
    version = "unknown"
    vfile = checkout / "comfyui_version.py"
    if vfile.exists():
        for line in vfile.read_text().splitlines():
            if line.startswith("__version__"):
                version = "v" + line.split("=", 1)[1].strip().strip('"\'')
    head = checkout / ".git" / "HEAD"
    commit = head.read_text().strip() if head.exists() else "unknown"
    if commit.startswith("ref: "):
        ref = checkout / ".git" / commit[5:]
        commit = ref.read_text().strip() if ref.exists() else commit
    return f"ComfyUI {version} ({commit})"


def first_seed(graph: dict):
    for nid in sorted(graph, key=lambda k: (0, int(k), "") if k.isdigit() else (1, 0, k)):
        inputs = graph[nid].get("inputs", {})
        if graph[nid]["class_type"].startswith("KSampler") and isinstance(inputs.get("seed"), int):
            return inputs["seed"]
    return None


def literal_params(graph: dict) -> dict:
    return {nid: {"class_type": node["class_type"],
                  **{k: v for k, v in node.get("inputs", {}).items() if not isinstance(v, list)}}
            for nid, node in sorted(graph.items())}


def licence_text(found: list, table: dict) -> str:
    names = table["licences"]
    parts = sorted({names[p["licence"]]["name"] for row, _ in found for p in row["parts"]})
    lines = [f"Generated locally by the ComfyUI TRELLIS.2 lane from models under: {', '.join(parts)}.",
             "Generated with GPL-3.0 tooling (ComfyUI); on the common reading the GPL does not reach outputs."]
    credits = sorted({row["credit"] for row, _ in found if row.get("credit")})
    if credits:
        lines.append("Credit line for products that ship this asset: " + "; ".join(credits) + ".")
    for row, _ in found:
        lines.extend(row.get("conditions", []))
    lines.append("Conditional: see asset-harness 3d-static-props/findings/2026-09-23-trellis2-lane-licence.md.")
    return " ".join(lines)


def build(glb: Path, graph: dict, models: Path, checkout: Path, table: dict, custom_nodes=None) -> dict:
    found = components_for(graph, models, table)
    arm = next(r["generator"] for r, _ in found if "generator" in r)
    deps = [{"name": row["file"], "content_hash": sha256_file(path), "bytes": path.stat().st_size,
             "source": row["source"]} for row, path in found]
    for name in (custom_nodes if custom_nodes is not None else CUSTOM_NODES):
        init = checkout / "custom_nodes" / name / "__init__.py"
        if init.exists():
            deps.append({"name": f"custom_nodes/{name}/__init__.py", "content_hash": sha256_file(init)})
        elif custom_nodes is not None:
            raise Refused(f"custom node {name} is not in {checkout / 'custom_nodes'}")
    size_notes = [f"{d['name']}: {d['bytes']} bytes on disk, {d['source']['size']} at the source"
                  for d in deps if "source" in d and d["bytes"] != d["source"].get("size")]
    return {
        "asset": {"file": glb.name, "bytes": glb.stat().st_size, "content_hash": sha256_file(glb)},
        "lane": LANE,
        "arm": arm,
        "license_record": {
            "status": "conditional",
            "commercial_in_game": True,
            "standalone_redistributable": True,
            "source": {"kind": "local-generation",
                       "note": f"ComfyUI TRELLIS.2 lane, {arm} arm; licence rows read {table['read']}"},
            "text": licence_text(found, table),
            "components": [{"file": row["file"], "role": row["role"], "source": row["source"],
                            "parts": row["parts"]} for row, _ in found],
            "size_mismatches": size_notes,
        },
        "provenance": {
            "source_of_truth": "provider-nondeterministic",
            "generator_script": "3d-static-props/prototypes/trellis2-comfyui/run_api_graph.py",
            "recipe": {
                "provider": "comfyui-core",
                "generator": arm,
                "generator_version": checkout_version(checkout),
                "params": literal_params(graph),
                "seed": first_seed(graph),
                "dependencies": deps,
                "salt": SALT,
            },
        },
    }


def schema_errors(record: dict, contracts: Path) -> list:
    sys.path.insert(0, str(contracts))
    import contracts_validator  # noqa: PLC0415 — vendored, stdlib-only
    schema = json.loads((contracts / "contracts-3.schema.json").read_text())
    return (contracts_validator.validate_ref(schema, "#/definitions/licenseRecord", record["license_record"])
            + contracts_validator.validate_ref(schema, "#/definitions/provenance", record["provenance"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("glb", type=Path)
    ap.add_argument("graph", type=Path)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--checkout", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--custom-nodes", help="comma-separated custom-node packages the run loaded")
    ap.add_argument("--licences", type=Path, default=HERE / "lane_licences.json")
    ap.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    a = ap.parse_args(argv)
    out = a.out or a.glb.with_name(a.glb.name + ".lane.json")
    try:
        nodes = [n for n in a.custom_nodes.split(",") if n] if a.custom_nodes is not None else None
        record = build(a.glb, json.loads(a.graph.read_text()), a.models, a.checkout,
                       json.loads(a.licences.read_text()), nodes)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    errors = schema_errors(record, a.contracts)
    if errors:
        print("INVALID: " + "; ".join(errors), file=sys.stderr)
        return 1
    tmp = out.with_name(out.name + ".part")
    tmp.write_text(json.dumps(record, indent=1) + "\n")
    os.replace(tmp, out)
    print(f"wrote {out} ({record['arm']}, {len(record['provenance']['recipe']['dependencies'])} dependencies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
