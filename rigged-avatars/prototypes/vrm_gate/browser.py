"""Gate stage: what a consumer resolves. three-vrm loads the file in headless Chromium, reports which
morph influences each expression drives, and renders the contact sheet.

No Node and no puppeteer: the page writes its results into the DOM and `chromium --dump-dom` prints it.
"""
import base64
import functools
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import arkit52

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
FRAME = 320
COLUMNS = 8
# Framing, in units of the distance between the eye bones: the frame is this many spans tall, centred
# this far below the eye line, which puts brows to chin in frame on a head of ordinary proportions.
HEIGHT_IN_EYE_SPANS = 3.7
DROP_BELOW_EYES = 0.45
# An authored expression must change at least this many pixels against the same run's neutral frame.
# On the v1 rig at this frame size the subtlest authored shape changes about 630 and a flattened one
# changes 0, so the floor sits far from both.
MIN_CHANGED_PIXELS = 100
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# Spring simulation, tip movement relative to the head, in metres. Measured on the v1 rig in three-vrm 3.5.5
# at a 1/60 s step: a 35 degree head turn swings the tips 49-92 mm with `center` on the hips and 0.0-0.3 mm
# with it on the head; an eased 3 m move of the whole avatar moves them 0.0-0.3 mm with a centre and
# 181-305 mm without one; a 55 degree head roll leaves the nearest joint 1.4 mm inside the collider surface
# with the collider and 29.0 mm inside without it.
SWAY_FLOOR = 0.010
TRANSLATE_CEILING = 0.005
PENETRATION_TOLERANCE = 0.002


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _chromium():
    # VRM_GATE_CHROMIUM names the browser binary outright, for hosts that package it differently.
    override = os.environ.get("VRM_GATE_CHROMIUM")
    if override:
        return shutil.which(override)
    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _extract(dom, element_id):
    m = re.search(rf'<pre id="{element_id}">(.*?)</pre>', dom, re.S)
    return html.unescape(m.group(1)) if m else None


def _render(vrm_path, job):
    """Serve the page on loopback, run Chromium once, return (result dict, sheet PNG bytes or None)."""
    chromium = _chromium()
    if chromium is None:
        raise RuntimeError("no chromium on PATH")
    for needed in (VENDOR / "three" / "three.module.js", VENDOR / "three-vrm.module.js"):
        if not needed.is_file():
            raise RuntimeError(f"{needed} is missing — run ./fetch_vendor.sh")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.html").symlink_to(HERE / "page.html")
        (root / "vendor").symlink_to(VENDOR)
        (root / "asset.vrm").symlink_to(Path(vrm_path).resolve())
        (root / "job.json").write_text(json.dumps(job))
        handler = functools.partial(_Quiet, directory=str(root))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/page.html"
            proc = subprocess.run(
                [chromium, "--headless=new", "--disable-gpu", "--use-angle=swiftshader",
                 "--enable-unsafe-swiftshader", "--hide-scrollbars", f"--user-data-dir={root / 'profile'}",
                 "--virtual-time-budget=300000", "--dump-dom", url],
                capture_output=True, text=True, timeout=900)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
    raw = _extract(proc.stdout, "result")
    if raw is None or raw == "PENDING":
        raise RuntimeError(f"the page produced no result (chromium exit {proc.returncode}): "
                           f"{(proc.stderr or '').strip()[-300:]}")
    result = json.loads(raw)
    sheet = _extract(proc.stdout, "sheet") or ""
    png = base64.b64decode(sheet.split(",", 1)[1]) if sheet.startswith("data:image/png;base64,") else None
    return result, png


def _springs_job(v1, archetype):
    """What the page needs to find the chains and the collider: node indices, since three.js renames nodes."""
    want = arkit52.ARCHETYPE_SPRINGS.get(archetype)
    sb = (v1.glb.json.get("extensions") or {}).get("VRMC_springBone")
    if want is None or not sb:
        return None
    try:
        chains = {s["name"]: {"joints": [j["node"] for j in s["joints"]],
                              "hitRadius": max(j.get("hitRadius", 0.0) for j in s["joints"])}
                  for s in sb["springs"] if s.get("name") in want["chains"]}
        group = next(g for g in sb["colliderGroups"] if g.get("name") == want["collider_group"])
        sphere = sb["colliders"][group["colliders"][0]]["shape"]["sphere"]
        return {"chains": chains, "collider": {"offset": sphere["offset"], "radius": sphere["radius"]}}
    except (KeyError, IndexError, StopIteration, TypeError):
        return None


def _spring_rows(report, sim, asked, archetype):
    st = "consumer"
    if arkit52.ARCHETYPE_SPRINGS.get(archetype) is None:
        return
    if not asked or not sim:
        report.add(st, "three-vrm simulates the spring chains", False,
                   "the file's VRMC_springBone block could not be handed to the page" if not asked
                   else "the page returned no simulation")
        return
    mm = lambda scenario: {k: round(v * 1000, 1) for k, v in sim[scenario]["peakTipMoveVsHead"].items()}
    expected_joints = sum(len(c["joints"]) - 1 for c in asked["chains"].values())
    report.add(st, "three-vrm simulates every joint but each chain's end marker",
               sim["joints"] == expected_joints, f"{sim['joints']} spring joints, {expected_joints} expected")
    report.add(st, "at rest the chains stay finite and still",
               sim["settle"]["finite"] and max(sim["settle"]["peakTipMoveVsHead"].values()) < 0.001,
               f"tip movement over 120 steps {mm('settle')} mm")
    # Presence before absence: the two rows after this one assert that the hair does NOT move or penetrate,
    # which a rig whose springs never run would also satisfy.
    report.add(st, "a head turn swings every chain",
               min(sim["sway"]["peakTipMoveVsHead"].values()) >= SWAY_FLOOR,
               f"tips move {mm('sway')} mm relative to the head (floor {SWAY_FLOOR * 1000:.0f} mm)")
    report.add(st, "moving the whole avatar does not throw the chains",
               sim["translate"]["finite"] and max(sim["translate"]["peakTipMoveVsHead"].values()) <= TRANSLATE_CEILING,
               f"tips move {mm('translate')} mm during an eased 3 m move (ceiling {TRANSLATE_CEILING * 1000:.0f} mm)")
    worst = min(sim["tilt"]["minClearance"], sim["tiltOther"]["minClearance"])
    report.add(st, "rolling the head onto either shoulder leaves the hair outside the head collider",
               worst >= -PENETRATION_TOLERANCE,
               f"nearest joint {worst * 1000:+.1f} mm from the collider surface, hit radius included "
               f"(tolerance {PENETRATION_TOLERANCE * 1000:.0f} mm)")


def run(report, vrm_path, v1, archetype, out_dir):
    """Returns False when the stage could not run at all."""
    st = "consumer"
    authored = arkit52.ARCHETYPES[archetype]
    stubs = arkit52.stub_names(authored)
    composed = [arkit52.vrm1_json_key(p) for p in arkit52.PRESET_COMPOSITION]
    job = {"frame": FRAME, "columns": COLUMNS, "sheet": list(authored) + composed,
           "heightInEyeSpans": HEIGHT_IN_EYE_SPANS, "dropBelowEyes": DROP_BELOW_EYES,
           "springs": _springs_job(v1, archetype)}
    try:
        result, png = _render(vrm_path, job)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        report.add(st, "three-vrm loads the file in headless Chromium", False, str(e))
        return False
    if not report.add(st, "three-vrm loads the file in headless Chromium", result.get("ok") is True,
                      result.get("error") or f"{result.get('renderer')}, three r{result.get('three')}"):
        return False

    seen = result["expressions"]
    want_names = sorted([arkit52.vrm1_json_key(p) for p in arkit52.VRM1_PRESETS] + list(arkit52.ARKIT_52))
    report.add(st, "three-vrm exposes exactly the contract's 70 expressions", sorted(result["names"]) == want_names,
               f"{len(result['names'])} expressions")

    custom = v1.vrm["expressions"]["custom"]
    preset = v1.vrm["expressions"]["preset"]

    def expected(expression):
        out = {}
        for bind in expression.get("morphTargetBinds", []):
            _, index, _ = v1.resolve(bind)
            out[str(index)] = out.get(str(index), 0.0) + bind.get("weight", 1.0)
        return out

    def drives(name, expression):
        got = seen[name]["influences"]
        want = expected(expression)
        ok = (seen[name]["primitivesAgree"] and set(got) == set(want)
              and all(abs(got[k] - want[k]) < 1e-6 for k in want))
        return ok, f"three-vrm drives {got}, the file binds {want}"

    for name in authored:
        report.guarded(st, f"{name}: three-vrm drives the target the file binds",
                       lambda name=name: drives(name, custom[name]))
    for name in stubs:
        report.guarded(st, f"{name}: three-vrm drives only what the file binds (stub)",
                       lambda name=name: drives(name, custom[name]))
    for key in composed:
        report.guarded(st, f"preset {key}: three-vrm drives its composition",
                       lambda key=key: drives(key, preset[key]))

    report.add(st, "the renderer is deterministic within a run (neutral rendered twice)",
               result["neutralRepeatChangedPixels"] == 0,
               f"{result['neutralRepeatChangedPixels']} pixels differ between two neutral frames")
    report.add(st, "the neutral frame shows the avatar", result["neutralLitPixels"] > FRAME * FRAME * 0.15,
               f"{result['neutralLitPixels']} of {FRAME * FRAME} pixels differ from the same frame "
               f"with the avatar hidden")
    for name in authored:
        n = seen.get(name, {}).get("changedPixels", 0)
        report.add(st, f"{name}: the rendered frame differs from neutral", n >= MIN_CHANGED_PIXELS,
                   f"{n} pixels changed (floor {MIN_CHANGED_PIXELS})")
    for name in stubs:
        n = seen.get(name, {}).get("changedPixels", -1)
        report.add(st, f"{name}: the rendered frame is identical to neutral (stub)", n == 0, f"{n} pixels changed")

    _spring_rows(report, result.get("springs"), job["springs"], archetype)

    sheet_path = Path(out_dir) / "contact_sheet.png"
    want_frames = 1 + len(job["sheet"])
    ok = png is not None and png.startswith(PNG_MAGIC) and len(result["sheet"]["frames"]) == want_frames
    if ok:
        sheet_path.write_bytes(png)
    report.add(st, "the contact sheet has one frame per authored expression", ok,
               f"{sheet_path} — {result['sheet']['width']}x{result['sheet']['height']}, "
               f"{len(result['sheet']['frames'])} frames (neutral, {len(authored)} authored, "
               f"{len(composed)} composed presets)" if ok else "no PNG came back from the page")
    (Path(out_dir) / "consumer_result.json").write_text(json.dumps(result, indent=1))
    return True
