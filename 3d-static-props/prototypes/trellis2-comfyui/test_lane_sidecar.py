#!/usr/bin/env python3
"""Tests for lane_sidecar.py, plain `python3 test_lane_sidecar.py`, host python3, no pytest.

Fixture graphs and small stand-in model files under a temporary models tree, named like the lane's
real files so the real lane_licences.json applies. Nothing reads a GPU or the network.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lane_sidecar as S  # noqa: E402

FAILS = []
DINO = "clip_vision/dino_v3_L_naf_fp32.safetensors"
TABLE = json.loads((HERE / "lane_licences.json").read_text())


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def graph(unet="trellis_2_int8_convrot.safetensors", dino=True, extra=None):
    g = {
        "3": {"class_type": "KSampler", "inputs": {"seed": 56, "steps": 12, "model": ["40", 0]}},
        "12": {"class_type": "KSampler", "inputs": {"seed": 43}},
        "316:5": {"class_type": "PrimitiveBoolean", "inputs": {"value": True}},
        "40": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "117": {"class_type": "VAELoader", "inputs": {"vae_name": "trellis_2_shape_vae_bf16.safetensors"}},
        "193": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}},
    }
    if dino:
        g["15"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "dino_v3_L_naf_fp32.safetensors"}}
    g.update(extra or {})
    return g


def tree(root: Path, extra_files=()):
    models = root / "models"
    for row in TABLE["components"]:
        p = models / row["file"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(row["file"].encode())
    for rel in extra_files:
        p = models / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"unrecorded")
    checkout = root / "ComfyUI"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "HEAD").write_text("8fed37813848259fbdd2548ae3cd9f14df7fd68b\n")
    (checkout / "comfyui_version.py").write_text('__version__ = "0.34.6"\n')
    guard = checkout / "custom_nodes" / "rocm_unwrap_guard"
    guard.mkdir(parents=True)
    (guard / "__init__.py").write_text("# guard\n")
    glb = root / "asset.glb"
    glb.write_bytes(b"glTF-stand-in")
    return models, checkout, glb


def run(root, g, models, checkout, glb):
    gp = root / "graph.json"
    gp.write_text(json.dumps(g))
    out = root / "asset.glb.lane.json"
    out.unlink(missing_ok=True)
    rc = S.main([str(glb), str(gp), "--models", str(models), "--checkout", str(checkout)])
    return rc, (json.loads(out.read_text()) if out.exists() else None)


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main():
    print("lane_sidecar")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        models, checkout, glb = tree(root, extra_files=["diffusion_models/unrecorded_model.safetensors"])

        # the record's content
        rc, rec = run(root, graph(), models, checkout, glb)
        check("a TRELLIS.2 graph gets a sidecar", rc == 0 and rec is not None, rc)
        lr, pv = rec["license_record"], rec["provenance"]
        check("asset hash is the GLB's", rec["asset"]["content_hash"] == sha(b"glTF-stand-in"), rec["asset"])
        check("the arm is the generator's", rec["arm"] == "trellis2" and pv["recipe"]["generator"] == "trellis2", rec["arm"])
        check("status conditional, both booleans true",
              (lr["status"], lr["commercial_in_game"], lr["standalone_redistributable"]) == ("conditional", True, True), lr)
        check("source kind is local-generation", lr["source"]["kind"] == "local-generation", lr["source"])
        check("the note carries the rows' read date", TABLE["read"] in lr["source"]["note"], lr["source"]["note"])
        check("provenance is provider-nondeterministic", pv["source_of_truth"] == "provider-nondeterministic", pv)
        deps = {x["name"]: x for x in pv["recipe"]["dependencies"]}
        check("every loaded model is a dependency with its sha256",
              deps.get(DINO, {}).get("content_hash") == sha(DINO.encode())
              and "vae/trellis_2_shape_vae_bf16.safetensors" in deps
              and "background_removal/birefnet.safetensors" in deps, sorted(deps))
        check("a model the graph does not load is not a dependency",
              "geometry_estimation/moge_2_vitl_normal_fp16.safetensors" not in deps, sorted(deps))
        check("an installed guard is a dependency", "custom_nodes/rocm_unwrap_guard/__init__.py" in deps, sorted(deps))
        check("the ComfyUI version and commit are recorded",
              pv["recipe"]["generator_version"] == "ComfyUI v0.34.6 (8fed37813848259fbdd2548ae3cd9f14df7fd68b)",
              pv["recipe"]["generator_version"])
        check("the seed is the first sampler's", pv["recipe"]["seed"] == 56, pv["recipe"]["seed"])
        check("params carry literal inputs, not links",
              pv["recipe"]["params"]["3"] == {"class_type": "KSampler", "seed": 56, "steps": 12}, pv["recipe"]["params"]["3"])
        check("the components list names the conditioner's two parts",
              [p["licence"] for c in lr["components"] if c["file"] == DINO for p in c["parts"]] == ["dinov3", "apache-2.0"])
        check("stand-in sizes are reported as mismatches, not refused", len(lr["size_mismatches"]) == 4, lr["size_mismatches"])

        # schema validation, and a record that fails it
        check("the written record validates", S.schema_errors(rec, S.DEFAULT_CONTRACTS) == [])
        bad = json.loads(json.dumps(rec))
        bad["license_record"]["status"] = "maybe"
        check("a status outside the enum fails validation", S.schema_errors(bad, S.DEFAULT_CONTRACTS) != [])
        rc, rec2 = run(root, graph(extra={"9": {"class_type": "X", "inputs": {"api_key": "x"}}}), models, checkout, glb)
        check("an invalid record exits 1 and writes nothing", rc == 1 and rec2 is None, rc)

        # refusals
        rc, rec3 = run(root, graph(unet="unrecorded_model.safetensors"), models, checkout, glb)
        check("a graph loading an unrecorded model is refused (exit 2), nothing written", rc == 2 and rec3 is None, rc)
        try:
            S.components_for(graph(unet="unrecorded_model.safetensors"), models, TABLE)
            msg = ""
        except S.Refused as exc:
            msg = str(exc)
        check("the refusal names the unrecorded file", "diffusion_models/unrecorded_model.safetensors" in msg, msg)
        extra_vae = {"118": {"class_type": "VAELoader", "inputs": {"vae_name": "unrecorded_model.safetensors"}}}
        rc, rec3b = run(root, graph(extra=extra_vae), models, checkout, glb)
        check("an unrecorded non-generator model is refused too", rc == 2 and rec3b is None, rc)
        two = graph(extra={"319": {"class_type": "UNETLoader", "inputs": {"unet_name": "pixal3d_int8_convrot.safetensors"}}})
        rc, rec4 = run(root, two, models, checkout, glb)
        check("a graph with two generators is refused", rc == 2 and rec4 is None, rc)
        birefnet = models / "background_removal" / "birefnet.safetensors"
        kept = birefnet.read_bytes()
        birefnet.unlink()
        try:
            rc, rec5 = run(root, graph(), models, checkout, glb)
        except OSError as exc:
            rc, rec5 = f"raised {exc.__class__.__name__}", None
        birefnet.write_bytes(kept)
        check("a recorded model file missing from disk is refused", rc == 2 and rec5 is None, rc)
        dup = models / "vae" / "birefnet.safetensors"
        dup.write_bytes(b"same name, other directory")
        rc, rec6 = run(root, graph(), models, checkout, glb)
        dup.unlink()
        check("a model name matching two files is refused", rc == 2 and rec6 is None, rc)

        gp = root / "graph.json"
        gp.write_text(json.dumps(graph()))
        out = root / "asset.glb.lane.json"
        out.unlink(missing_ok=True)
        rc = S.main([str(glb), str(gp), "--models", str(models), "--checkout", str(checkout), "--custom-nodes", ""])
        named = json.loads(out.read_text()) if out.exists() else None
        check("--custom-nodes '' records no custom node", rc == 0 and named and not any(
            x["name"].startswith("custom_nodes/") for x in named["provenance"]["recipe"]["dependencies"]), rc)
        out.unlink(missing_ok=True)
        rc = S.main([str(glb), str(gp), "--models", str(models), "--checkout", str(checkout), "--custom-nodes", "mem_probe"])
        check("a named custom node missing from the checkout is refused", rc == 2 and not out.exists(), rc)

        # the credit line follows the DINOv3 component
        credit = "Built with DINOv3"
        check("the credit line is in the text when DINOv3 is loaded", credit in rec["license_record"]["text"])
        rc, nodino = run(root, graph(dino=False), models, checkout, glb)
        check("a graph without DINOv3 still gets a sidecar", rc == 0 and nodino is not None, rc)
        check("and its text has no credit line", credit not in nodino["license_record"]["text"])
        check("and no DINOv3 licence among its parts",
              all(p["licence"] != "dinov3" for c in nodino["license_record"]["components"] for p in c["parts"]))

    print(f"{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all ok'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
