#!/usr/bin/env python3
"""Characterization tests for build_atlas.py — plain python3, stdlib + PIL, no pytest.

Run:  python3 test_build_atlas.py
Exits 0 if every check passes, non-zero if any fails, so it can gate a commit. Pins the
current trim / alpha-threshold / shelf-pack / grid-mode behavior of build_atlas so future
edits have a cheap regression anchor. All fixtures are synthetic and built in a temp dir
(no ComfyUI, no network, no real generated assets).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_ATLAS = HERE / "build_atlas.py"
sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402  (import after sys.path insert)
import build_atlas  # noqa: E402

_results = []


def check(name, cond, detail=""):
    _results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{' - ' + detail if detail else ''}")


def make_sprite(size, subject, subject_alpha=255, specks_alpha=0, fill=(180, 120, 60)):
    """Transparent size x size RGBA with an opaque subject rect subject=(l,t,r,b);
    optional single-pixel corner specks at specks_alpha (for the WI 814 matting cases)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    l, t, r, b = subject
    im.paste(Image.new("RGBA", (r - l, b - t), (*fill, subject_alpha)), (l, t))
    if specks_alpha:
        for (x, y) in [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]:
            im.putpixel((x, y), (10, 10, 10, specks_alpha))
    return im


def run_pipeline(work, sprites, extra_args):
    """Write sprites {name: Image} + a manifest under `work`, run build_atlas.py as a
    subprocess (the real CLI entry point), and return (descriptor dict, outdir)."""
    indir = work / "in"
    outdir = work / "out"
    indir.mkdir(parents=True)
    ships = []
    for name, im in sprites.items():
        im.save(indir / f"{name}.png")
        ships.append({"name": name, "rgba": f"{name}.png"})
    (work / "manifest.json").write_text(json.dumps({"ships": ships}))
    cmd = [sys.executable, str(BUILD_ATLAS),
           "--manifest", str(work / "manifest.json"), "--indir", str(indir),
           "--outdir", str(outdir), "--name", "test"] + extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"build_atlas exited {proc.returncode}: {proc.stderr.strip()}")
    return json.loads((outdir / "test.json").read_text()), outdir


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        SUBJECT = (200, 150, 300, 250)  # 100x100

        # --- Unit: default trim + downscale (trim_and_fit) ---
        small = tmp / "small.png"
        make_sprite(512, SUBJECT).save(small)
        check("trim_and_fit crops to subject bbox (100x100)",
              build_atlas.trim_and_fit(small, 256).size == (100, 100))

        big = tmp / "big.png"
        make_sprite(1024, (100, 100, 900, 900)).save(big)  # 800x800 subject > max-dim
        check("trim_and_fit downscales largest dim to max-dim (256)",
              max(build_atlas.trim_and_fit(big, 256).size) == 256)

        # --- Unit: alpha-threshold speck robustness (WI 814) ---
        speck = tmp / "speck.png"
        make_sprite(512, SUBJECT, specks_alpha=4).save(speck)
        check("threshold ignores sub-threshold specks -> tight subject",
              build_atlas.trim_and_fit(speck, 256, alpha_threshold=8).size == (100, 100))
        check("threshold 0 = legacy: specks keep full frame (downscaled to 256)",
              build_atlas.trim_and_fit(speck, 256, alpha_threshold=0).size == (256, 256))

        at_thr = tmp / "at.png"
        make_sprite(512, SUBJECT, specks_alpha=8).save(at_thr)
        check("speck alpha == threshold is kept (full frame)",
              build_atlas.trim_and_fit(at_thr, 256, alpha_threshold=8).size == (256, 256))

        below = tmp / "below.png"
        make_sprite(512, SUBJECT, specks_alpha=7).save(below)
        check("speck alpha == threshold-1 is ignored (tight)",
              build_atlas.trim_and_fit(below, 256, alpha_threshold=8).size == (100, 100))

        # --- Unit: shelf_pack ---
        pls, _, ah = build_atlas.shelf_pack([(50, 40)], 1024)
        check("shelf_pack single frame: one placement at origin",
              pls == [(0, 0)] and ah == 40, f"{pls} h={ah}")

        pls, _, ah = build_atlas.shelf_pack([(600, 30), (600, 50)], 1024)
        check("shelf_pack wraps when next frame exceeds atlas width",
              pls[0] == (0, 0) and pls[1][0] == 0 and pls[1][1] > 0, str(pls))
        check("shelf_pack atlas height spans both shelves",
              ah == 30 + build_atlas.PAD + 50, f"h={ah}")

        # --- Integration: grid (--cell) mode keeps the full square cell ---
        descr, _ = run_pipeline(tmp / "grid", {
            "a": make_sprite(300, (50, 50, 250, 250)),
            "b": make_sprite(300, (80, 80, 200, 200)),
        }, ["--cell", "64", "--cols", "2"])
        check("grid mode: every frame is exactly cell x cell (64)",
              all(f["frame"]["w"] == 64 and f["frame"]["h"] == 64 for f in descr["frames"].values()),
              str({k: (v["frame"]["w"], v["frame"]["h"]) for k, v in descr["frames"].items()}))
        check("grid mode: descriptor lists every manifest entry",
              set(descr["frames"]) == {"a", "b"}, str(set(descr["frames"])))

        # --- Integration: default mode trims a speckly frame + emits a valid atlas ---
        descr, outdir = run_pipeline(tmp / "dflt", {
            "s": make_sprite(512, SUBJECT, specks_alpha=4),
        }, ["--max-dim", "256", "--alpha-threshold", "8"])
        f = descr["frames"]["s"]["frame"]
        check("default mode: speckly frame trims to subject (100x100), not full frame",
              (f["w"], f["h"]) == (100, 100), f"{f['w']}x{f['h']}")
        check("default mode: atlas PNG written", (outdir / "test.png").exists())
        check("default mode: descriptor has meta + frames",
              "meta" in descr and "frames" in descr)

    passed, total = sum(_results), len(_results)
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
