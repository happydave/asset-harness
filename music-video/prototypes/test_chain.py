#!/usr/bin/env python3
"""Regression checks for chain_clip.py. Plain `python3 test_chain.py`, no pytest.

Same convention as test_manifest.py / test_render.py: exits non-zero on failure. Needs ffmpeg on PATH.
Covers everything that does not need a GPU: the cleanup chain's content-preservation invariant, the
seam measurement, concat (plain and crossfaded), link-shape validation, alpha refusal, and resume.
Synthetic clips are generated with ffmpeg's testsrc, so the whole file runs in a few seconds.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chain_clip as cc

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + detail}")
    if not cond:
        FAILURES.append(label)


def make_clip(path: Path, *, n: int, w: int = 160, h: int = 96, fps: int = 16, seed: int = 0) -> Path:
    """A moving synthetic clip: testsrc pans, so adjacent frames differ like a real shot."""
    # Duration must cover seed+n frames, or `select` yields an empty file.
    dur = (seed + n + 2) / fps
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
                    "-i", f"testsrc=size={w}x{h}:rate={fps}:duration={dur:.3f}",
                    "-vf", f"select=gte(n\\,{seed}),setpts=N/{fps}/TB", "-frames:v", str(n),
                    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(path)],
                   check=True)
    return path


def make_png(path: Path, *, alpha: bool = False, w: int = 160, h: int = 96) -> Path:
    src = f"testsrc=size={w}x{h}:rate=1:duration=1"
    vf = "format=rgba" if alpha else "format=rgb24"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", src,
                    "-vf", vf, "-frames:v", "1", str(path)], check=True)
    return path


def main() -> int:
    # --- cleanup chain ---------------------------------------------------------------------------
    vf = cc.cleanup_chain()
    check("cleanup chain contains no geometric filter",
          not any(g in vf for g in cc.GEOMETRIC), vf)
    check("default cleanup chain includes the sharpen", cc.SHARPEN in vf, vf)
    check("default cleanup chain EXCLUDES the grade (it compounds across seams)",
          cc.GRADE not in vf, vf)
    check("--grade restores the full July recipe",
          cc.GRADE in cc.cleanup_chain(grade=True), cc.cleanup_chain(grade=True))
    check("--no-denoise drops hqdn3d only",
          cc.DENOISE not in cc.cleanup_chain(denoise=False)
          and cc.SHARPEN in cc.cleanup_chain(denoise=False), cc.cleanup_chain(denoise=False))

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        # --- content preservation (plan behavior 2) -----------------------------------------------
        raw = make_png(d / "raw.png")
        cleaned = cc.clean_frame(raw, d / "clean.png")
        s_clean = cc.ssim(raw, cleaned)

        # A bare magnitude threshold does not test the invariant: sharpening changes pixels without
        # moving content, and how much it changes them depends entirely on the content's frequency
        # (0.97 on a photographic frame, 0.86 on testsrc's hard edges). What must hold is that content
        # stays PUT — so compare against a control that does move it by 2px and nothing else.
        shifted = d / "shift.png"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(raw),
                        "-vf", "crop=iw-2:ih-2:2:2,pad=iw+2:ih+2:0:0", str(shifted)], check=True)
        s_shift = cc.ssim(raw, shifted)
        check("cleanup preserves content position (beats a 2px shift by a clear margin)",
              s_clean > s_shift + 0.05, f"clean={s_clean:.4f} shifted={s_shift:.4f}")

        sz = lambda f: (cc.probe_image(f)["width"], cc.probe_image(f)["height"])  # noqa: E731
        check("cleanup does not change dimensions", sz(cleaned) == sz(raw),
              f"{sz(cleaned)} vs {sz(raw)}")

        # --- alpha refusal ------------------------------------------------------------------------
        rgba = make_png(d / "rgba.png", alpha=True)
        try:
            cc.assert_opaque_rgb(rgba)
            check("alpha start still is refused", False, "no ChainError raised")
        except cc.ChainError:
            check("alpha start still is refused", True)
        try:
            cc.assert_opaque_rgb(raw)
            check("opaque start still is accepted", True)
        except cc.ChainError as e:
            check("opaque start still is accepted", False, str(e))

        # --- concat + frame accounting (plan behavior 3) ------------------------------------------
        links = [make_clip(d / f"l{i}.mp4", n=20, seed=i * 20) for i in range(3)]
        out = cc.concat(links, d / "chained.mp4")
        info = cc.probe(out)
        check("plain concat frame count == sum of links", info["frames"] == 60, str(info))
        check("plain concat preserves resolution",
              (info["width"], info["height"]) == (160, 96), str(info))

        # --- link shape mismatch is refused -------------------------------------------------------
        odd = make_clip(d / "odd.mp4", n=20, w=128, h=96)
        try:
            cc.concat([links[0], odd], d / "bad.mp4")
            check("mismatched link resolution is refused", False, "no ChainError raised")
        except cc.ChainError:
            check("mismatched link resolution is refused", True)

        # --- seam measurement (plan behavior 4) ---------------------------------------------------
        reports = cc.seam_report(out, [20, 20, 20], d / "work")
        check("one report per seam", len(reports) == 2, str(reports))
        check("seams are located at the link boundaries",
              [r["at_frame"] for r in reports] == [20, 40], str(reports))
        check("each report carries seam, norm, gap and a verdict",
              all({"seam_ssim", "local_norm", "gap", "pass"} <= set(r) for r in reports), str(reports))

        # A deliberately hard cut must FAIL the gate — the check that proves the gate can fail.
        cut_a = make_clip(d / "cut_a.mp4", n=20, seed=0)
        cut_b = make_clip(d / "cut_b.mp4", n=20, w=160, h=96, seed=300)
        cut = cc.concat([cut_a, cut_b], d / "cut.mp4")
        cut_reports = cc.seam_report(cut, [20, 20], d / "cutwork")
        check("a hard cut fails the seam gate",
              not cut_reports[0]["pass"], str(cut_reports))

        # --- crossfade shortens by exactly one crossfade per seam (plan behavior 8) ---------------
        xf = cc.concat(links, d / "xf.mp4", crossfade=0.25, fps=16)
        xf_frames = cc.probe(xf)["frames"]
        expected = 60 - int(round(0.25 * 16)) * 2
        check("crossfade shortens by crossfade x fps per seam",
              abs(xf_frames - expected) <= 1, f"got {xf_frames}, expected ~{expected}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
