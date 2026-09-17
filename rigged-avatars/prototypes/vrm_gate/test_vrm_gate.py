#!/usr/bin/env python3
"""Tests for the VRM gate — plain python3, stdlib, no pytest.

Run:  python3 test_vrm_gate.py [--fast]
Exits non-zero if any check fails. `--fast` keeps to the reader's unit tests and the contract stage;
without it the mutation matrix also runs through the validator and headless Chromium (vendor/ needed).

The mutation matrix pins, per defect, the exact set of rows that fail. A defect that starts failing
more rows, or fewer, has moved a check's reach, and that is worth seeing even when the gate still exits 1.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mutate  # noqa: E402
from glb import Glb, GlbError  # noqa: E402

SAMPLE = HERE.parent.parent / "findings" / "samples-2026-09-07-v1-face-rig" / "v1_face_rig.vrm"
GATE = HERE / "vrm_gate.py"
FAST = "--fast" in sys.argv

failures = []


def check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# ---- synthetic GLBs ----------------------------------------------------------------------------------
def build_glb(doc, payload):
    payload += b"\x00" * (-len(payload) % 4)
    doc = dict(doc, buffers=[{"byteLength": len(payload)}])
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(payload)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(text), b"JSON") + text
            + struct.pack("<I4s", len(payload), b"BIN\x00") + payload)


def test_reader():
    print("reader")
    # three VEC3 elements interleaved with a 4-byte pad: stride 16
    strided = b"".join(struct.pack("<3f4x", *v) for v in ((1, 0, 0), (0, 3, 4), (0, 0, 2)))
    sparse_idx = struct.pack("<H", 2) + b"\x00\x00"
    sparse_val = struct.pack("<3f", 0, 0, 9)
    base = struct.pack("<9f", 1, 1, 1, 2, 2, 2, 3, 3, 3)
    payload = strided + sparse_idx + sparse_val + base
    o1, o2, o3 = len(strided), len(strided) + 4, len(strided) + 16
    doc = {
        "asset": {"version": "2.0"},
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(strided), "byteStride": 16},
                        {"buffer": 0, "byteOffset": o1, "byteLength": 2},
                        {"buffer": 0, "byteOffset": o2, "byteLength": 12},
                        {"buffer": 0, "byteOffset": o3, "byteLength": 36}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"componentType": 5126, "count": 4, "type": "VEC3",
             "sparse": {"count": 1, "indices": {"bufferView": 1, "componentType": 5123}, "values": {"bufferView": 2}}},
            {"bufferView": 3, "componentType": 5126, "count": 3, "type": "VEC3",
             "sparse": {"count": 1, "indices": {"bufferView": 1, "componentType": 5123}, "values": {"bufferView": 2}}},
        ],
        # parent turned 90 degrees about +Y, child one unit along its own +X: world position (0, 0, -1)
        "nodes": [{"rotation": [0, 0.7071067811865476, 0, 0.7071067811865476], "translation": [0, 0, 0],
                   "children": [1]},
                  {"translation": [1, 0, 0]}],
    }
    g = Glb(build_glb(doc, payload))
    check("dense accessor honours byteStride", list(g.accessor(0)) == [1, 0, 0, 0, 3, 4, 0, 0, 2])
    check("max_vec3_length finds the longest element", abs(g.max_vec3_length(0) - 5.0) < 1e-6)
    check("sparse accessor with no base view is zeros plus its values",
          list(g.accessor(1)) == [0, 0, 0, 0, 0, 0, 0, 0, 9, 0, 0, 0])
    check("sparse accessor over a base view overwrites only its indices",
          list(g.accessor(2)) == [1, 1, 1, 2, 2, 2, 0, 0, 9])
    x, y, z = g.world_position(1)
    check("a child's world position follows its parent's rotation",
          abs(x) < 1e-9 and abs(y) < 1e-9 and abs(z + 1) < 1e-9, f"{(x, y, z)}")

    whole = build_glb(doc, payload)
    for label, data in (("truncated file", whole[:-8]), ("wrong magic", b"glTX" + whole[4:]),
                        ("shorter than a header", b"glTF"),
                        ("accessor running past its view",
                         build_glb(dict(doc, accessors=[dict(doc["accessors"][0], count=4)]), payload))):
        try:
            Glb(data).accessor(0)
            refused = False
        except GlbError:
            refused = True
        check(f"refused: {label}", refused)


# ---- the gate as a command ---------------------------------------------------------------------------
SCRATCH = tempfile.TemporaryDirectory(prefix="vrm_gate_test_")


def gate(path, *flags, env=None):
    out = tempfile.mkdtemp(dir=SCRATCH.name)
    proc = subprocess.run([sys.executable, str(GATE), str(path), "--out", out, *flags],
                          capture_output=True, text=True, env=dict(os.environ, **(env or {})))
    report_path = Path(out) / "vrm_gate_report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else None
    return proc, report, Path(out)


def failed_rows(report):
    return sorted(f"{c['stage']}: {c['check']}" for c in report["checks"] if c["status"] == "fail")


# mutation -> rows that must fail, and no others. "consumer"/"validator" rows apply to the full run only.
EXPECTED = {
    "rename-key": ["contract: every morph target is an authored shape",
                   "contract: jawOpen binds its own morph, 1:1",
                   "contract: preset aa is composed as the contract says",
                   "contract: preset ee is composed as the contract says",
                   "contract: preset ih is composed as the contract says",
                   "contract: preset oh is composed as the contract says",
                   "contract: preset ou is composed as the contract says",
                   "contract: preset surprised is composed as the contract says"],
    "drop-bind": ["consumer: jawOpen: the rendered frame differs from neutral",
                  "contract: jawOpen binds its own morph, 1:1",
                  "contract: jawOpen displaces (authored)",
                  "contract: the bound customs are exactly the archetype's authored set"],
    "stub-bind": ["consumer: tongueOut: the rendered frame is identical to neutral (stub)",
                  "contract: the bound customs are exactly the archetype's authored set",
                  "contract: tongueOut displaces by exactly zero (stub)"],
    # The control on the control: a stub bound to a genuinely flat target keeps its zero-displacement row
    # green. The rule is about displacement, not about having no binds.
    "stub-flat": ["contract: every morph target is an authored shape",
                  "contract: the bound customs are exactly the archetype's authored set"],
    "stub-nonzero": ["contract: every morph target is an authored shape",
                     "contract: the bound customs are exactly the archetype's authored set",
                     "contract: tongueOut displaces by exactly zero (stub)"],
    "reindex": ["contract: jawOpen binds its own morph, 1:1",
                "contract: mouthPucker binds its own morph, 1:1"],
    "flatten": ["consumer: jawOpen: the rendered frame differs from neutral",
                "contract: jawOpen displaces (authored)"],
    "case-drift": ["consumer: eyeBlinkLeft: the rendered frame differs from neutral",
                   "consumer: eyeBlinkLeft: three-vrm drives the target the file binds",
                   "consumer: three-vrm exposes exactly the contract's 70 expressions",
                   "contract: customs are exactly the 52 ARKit names, exact case",
                   "contract: eyeBlinkLeft binds its own morph, 1:1",
                   "contract: eyeBlinkLeft displaces (authored)",
                   "contract: the bound customs are exactly the archetype's authored set",
                   "contract: the remaining customs are exactly the declared stubs"],
    "transpose-gaze": ["contract: the gaze origin matches the eye bones"],
    "wrong-weight": ["contract: preset ih is composed as the contract says"],
    # Invisible to the contract stage, which measures from the buffer; this one is the validator's.
    "bad-max": ["validator: bad-max.vrm has no glTF errors"],
}


def test_gate():
    print("gate on the committed sample")
    flags = ("--no-validator", "--no-browser") if FAST else ()
    proc, report, out = gate(SAMPLE, *flags)
    check("exits 0", proc.returncode == 0, proc.stdout[-400:])
    check("no failed rows", report is not None and failed_rows(report) == [])
    if report:
        ran = {k for k, v in report["stages"].items() if v == "ran"}
        check("every stage asked for is reported as ran",
              ran == ({"contract"} if FAST else {"validator", "contract", "consumer"}), str(report["stages"]))
        rows = {c["check"]: c for c in report["checks"]}
        stub = rows.get("tongueOut displaces by exactly zero (stub)", {})
        check("a stub's row states its bind count", "0 bind(s)" in stub.get("detail", ""))
        authored = rows.get("jawOpen displaces (authored)", {})
        check("an authored row states the measured figure and its floor",
              "mm in the file" in authored.get("detail", "") and "floor" in authored.get("detail", ""))
        check("the generator's own measurement was cross-checked, not skipped",
              rows.get("file displacement agrees with the generator's own measurement", {}).get("status") == "pass")
    if not FAST:
        png = out / "contact_sheet.png"
        ok = png.is_file() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", png.read_bytes()[16:24]) if ok else (0, 0)
        check("the contact sheet is a PNG of the reported size", ok and width == 8 * 320 and height > 320,
              f"{width}x{height}")

    print("switched-off stages are reported, not passed")
    proc, report, _ = gate(SAMPLE, "--no-validator", "--no-browser")
    off = [c for c in report["checks"] if c["status"] == "not-run"]
    check("two not-run rows, exit 0", proc.returncode == 0 and len(off) == 2 and report["not_run"] == 2)
    check("the totals line counts them apart from passes", "2 not run" in proc.stdout)

    print("a stage that cannot run fails the gate")
    proc, report, _ = gate(SAMPLE, "--no-browser", env={"VRM_GATE_VALIDATOR": "/nonexistent/gltf_validator"})
    check("missing validator: exit 1, stage could-not-run, fetch command named",
          proc.returncode == 1 and report["stages"]["validator"] == "could-not-run"
          and "fetch_vendor.sh" in proc.stdout)
    check("missing validator: it is a failed row, not a quiet not-run",
          failed_rows(report) == ["validator: glTF-Validator is available"])
    proc, report, _ = gate(SAMPLE, "--no-validator", env={"VRM_GATE_CHROMIUM": "no-such-browser"})
    check("missing browser: exit 1, stage could-not-run",
          proc.returncode == 1 and report["stages"]["consumer"] == "could-not-run")
    check("missing browser: it is a failed row",
          failed_rows(report) == ["consumer: three-vrm loads the file in headless Chromium"])
    # Completeness on its own: no failed row anywhere, and the gate still must not pass.
    import vrm_gate
    quiet = vrm_gate.Report()
    quiet.stages = {"validator": "could-not-run", "contract": "ran"}
    check("a stage that could not run fails the gate even with no failed row", quiet.ok is False)
    quiet.stages = {"validator": "off", "contract": "ran"}
    check("a stage switched off does not", quiet.ok is True)
    proc, report, _ = gate(SAMPLE, "--no-validator", env={"VRM_GATE_CHROMIUM": "true"})
    check("a browser that returns no result: exit 1, says so",
          proc.returncode == 1 and "produced no result" in proc.stdout)

    print("unreadable input")
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "short.vrm"
        bad.write_bytes(SAMPLE.read_bytes()[:5000])
        proc, report, _ = gate(bad, "--archetype", "stylized-v1", "--no-validator")
        check("one failed container row, the rest not run, no traceback",
              proc.returncode == 1 and failed_rows(report) == ["contract: short.vrm is a readable GLB"]
              and report["passed"] == 0 and "Traceback" not in proc.stderr + proc.stdout)
    proc, _, _ = gate(SAMPLE, "--archetype", "no-such-archetype", "--no-validator", "--no-browser")
    check("unknown archetype: exit 2, lists the known ones", proc.returncode == 2 and "stylized-v1" in proc.stdout)


def test_mutations():
    print("negative controls" + (" (contract stage only)" if FAST else " (all stages)"))
    # The predicate is tested, never the write: with the guard broken, a test that drove mutate() at the
    # sample would overwrite the committed file it is trying to protect.
    with tempfile.TemporaryDirectory() as tmp:
        original = Path(tmp) / "a.vrm"
        original.write_bytes(b"x")
        (Path(tmp) / "link.vrm").symlink_to(original)
        os.link(original, Path(tmp) / "hard.vrm")
        check("writing over the input is refused: same path", mutate.would_overwrite_input(original, original))
        check("writing over the input is refused: through a symlink",
              mutate.would_overwrite_input(original, Path(tmp) / "link.vrm"))
        check("writing over the input is refused: through a hard link",
              mutate.would_overwrite_input(original, Path(tmp) / "hard.vrm"))
        check("a fresh output path is allowed", not mutate.would_overwrite_input(original, Path(tmp) / "b.vrm"))
    with tempfile.TemporaryDirectory() as tmp:
        for name, rows in EXPECTED.items():
            broken = mutate.mutate(SAMPLE, Path(tmp) / f"{name}.vrm", name)
            flags = ("--no-validator", "--no-browser") if FAST else ()
            proc, report, _ = gate(broken, "--archetype", "stylized-v1", *flags)
            want = sorted(r for r in rows if r.startswith("contract:") or not FAST)
            got = failed_rows(report)
            check(f"{name}: fails exactly the expected rows", got == want,
                  f"unexpected {sorted(set(got) - set(want))}, missing {sorted(set(want) - set(got))}")
            check(f"{name}: exit {'1' if want else '0'}", proc.returncode == (1 if want else 0))
            broken.unlink()


if __name__ == "__main__":
    if not SAMPLE.is_file():
        raise SystemExit(f"sample missing: {SAMPLE}")
    test_reader()
    test_gate()
    test_mutations()
    SCRATCH.cleanup()
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all checks passed'}")
    raise SystemExit(1 if failures else 0)
