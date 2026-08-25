#!/usr/bin/env python3
"""Chain Wan i2v links into one continuous shot of arbitrary length (WI 1160).

Each link starts from the *cleaned last frame* of the link before it. Because i2v reproduces its start
frame closely (SSIM ~0.94, not 1.0), the seam is content-continuous rather than pixel-continuous — no
positional jump, a faint acuity lift. The cleanup pass is deliberately NOT generative: a low-denoise
img2img would restore more detail but shift content, which breaks the seam.

    python3 chain_clip.py --image start.png --links 3 --out flight \
        --prompt "gliding forward over the cloud sea, mist drifting past"

Resumable: links already on disk are reused, so an interrupted chain costs only its missing links.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comfy_client
import generate_clip as gc

# Recovered from the July chain_test pair (WI 1160): DENOISE+SHARPEN+GRADE applied to last_raw.png
# reproduces last_clean.png at SSIM 0.998. `hqdn3d` measured inert at this strength on a single frame
# (its temporal terms cannot apply); retained to match the original technique, droppable via
# --no-denoise.
DENOISE = "hqdn3d=1.5:1.5:3:3"

# SHARPEN is OFF by default (WI 1173). Like GRADE it is applied once per seam and COMPOUNDS, and it is
# by far the stronger offender: it raises a frame's acuity +83.5% in one application, and a measured
# 3-link chain stepped +25% per seam (1.39 -> 1.74 -> 2.16), i.e. +71% edge energy end to end. The owner
# saw it as over-sharpening at the first seam. It was carried over on the assumption that it compensated
# for a soft extracted frame; that is unsupported — PNG extraction of a decoded frame is lossless, so
# there is nothing to restore. Enable with --sharpen only to reproduce the July recipe.
SHARPEN = "unsharp=5:5:1.0:5:5:0.0"

# GRADE is OFF by default because it COMPOUNDS across seams. It is applied once per seam, so an N-link
# chain multiplies it N-1 times: a measured 3-link chain drifted from SATAVG 20.29 to 22.23 (+9.6%,
# ~1.05^2). The July chain was 2 links, applied it once, and never exposed this. Enable with --grade to
# reproduce the original recipe exactly; leave it off for chains longer than two links.
GRADE = "eq=contrast=1.05:saturation=1.05"

# Filters that move content. The cleanup chain must contain none of them (plan invariant); this is a
# proxy for "does not move content", not a proof — keep the chain short and readable.
GEOMETRIC = ("scale", "crop", "rotate", "perspective", "minterpolate", "zoompan", "pad", "transpose")

SEAM_TOLERANCE = 0.05    # max allowed drop below the local adjacent-frame SSIM mean
SEAM_WINDOW = 8          # frames before the seam used to establish that local norm

# Max allowed relative step in high-frequency energy across a seam. The SSIM gate alone passed a seam
# the owner could see was over-sharpened (gap -0.0002, its best result) because SSIM is dominated by
# structure and motion — a global acuity change barely registers. Within-link acuity varies by ~2%;
# the defect measured +25%. (WI 1173)
ACUITY_TOLERANCE = 0.10


class ChainError(RuntimeError):
    pass


def cleanup_chain(denoise: bool = True, grade: bool = False, sharpen: bool = False) -> str:
    parts = ([DENOISE] if denoise else []) + ([SHARPEN] if sharpen else []) + ([GRADE] if grade else [])
    if not parts:
        return "null"        # explicit identity; ffmpeg needs a filter
    vf = ",".join(parts)
    for f in GEOMETRIC:
        if f in vf:
            raise ChainError(f"cleanup chain contains geometric filter {f!r}: {vf}")
    return vf


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ChainError(f"{cmd[0]} failed: {r.stderr.strip()[:400]}")
    return r.stdout


def probe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,nb_frames,r_frame_rate", "-of", "json", str(path)])
    st = json.loads(out)["streams"][0]
    return {"width": int(st["width"]), "height": int(st["height"]),
            "frames": int(st["nb_frames"]), "fps": st["r_frame_rate"]}


def probe_image(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height", "-of", "json", str(path)])
    st = json.loads(out)["streams"][0]
    return {"width": int(st["width"]), "height": int(st["height"])}


def ssim(a: Path, b: Path) -> float:
    out = _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(a), "-i", str(b),
                "-lavfi", "ssim=stats_file=-", "-f", "null", "-"])
    for line in out.splitlines():
        if line.startswith("n:"):
            for tok in line.split():
                if tok.startswith("All:"):
                    return float(tok.split(":")[1])
    raise ChainError("could not parse ssim output")


def last_frame(clip: Path, out: Path) -> Path:
    n = probe(clip)["frames"]
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(clip),
          "-vf", f"select=eq(n\\,{n - 1})", "-vframes", "1", str(out)])
    if not out.is_file():
        raise ChainError(f"failed to extract last frame from {clip}")
    return out


def clean_frame(src: Path, out: Path, *, denoise: bool = True, grade: bool = False,
                sharpen: bool = False) -> Path:
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src),
          "-vf", cleanup_chain(denoise, grade, sharpen), str(out)])
    return out


LAPLACIAN = ("0 -1 0 -1 4 -1 0 -1 0:" * 4).rstrip(":")


def acuity(frame: Path) -> float:
    """Mean high-frequency (edge) energy of a frame. Higher = crisper."""
    out = _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(frame),
                "-vf", f"format=gray,convolution='{LAPLACIAN}',signalstats,metadata=print:file=-",
                "-frames:v", "1", "-f", "null", "-"])
    for line in out.splitlines():
        if "signalstats.YAVG" in line:
            return float(line.strip().split("=")[1])
    raise ChainError("could not parse acuity output")


ALPHA_PIX_FMTS = ("rgba", "bgra", "argb", "abgr", "ya8", "ya16", "yuva", "gbrap", "pal8")


def assert_opaque_rgb(img: Path) -> None:
    """Wan invents a background from an alpha channel — refuse before spending GPU time."""
    fmt = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(img)]).strip()
    if any(fmt.startswith(a) for a in ALPHA_PIX_FMTS):
        raise ChainError(f"{img} has an alpha channel (pix_fmt={fmt}); composite onto a background "
                         f"first — Wan spends its capacity inventing one otherwise")


def concat(links: list[Path], out: Path, *, crossfade: float = 0.0, fps: int = 16) -> Path:
    """Plain concat by default. A crossfade shortens the result by `crossfade` per seam."""
    shapes = [probe(l) for l in links]
    first = shapes[0]
    for l, sh in zip(links, shapes):
        if (sh["width"], sh["height"], sh["fps"]) != (first["width"], first["height"], first["fps"]):
            raise ChainError(f"link {l.name} is {sh['width']}x{sh['height']}@{sh['fps']}, "
                             f"expected {first['width']}x{first['height']}@{first['fps']}")
    if crossfade <= 0:
        listing = out.with_suffix(".concat.txt")
        listing.write_text("".join(f"file '{l.resolve()}'\n" for l in links))
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0",
              "-i", str(listing), "-c", "copy", str(out)])
        return out
    inputs: list[str] = []
    for l in links:
        inputs += ["-i", str(l)]
    steps, prev, off = [], "[0:v]", 0.0
    for i in range(1, len(links)):
        off += probe(links[i - 1])["frames"] / fps - crossfade
        lbl = f"[v{i}]"
        steps.append(f"{prev}[{i}:v]xfade=transition=fade:duration={crossfade}:offset={off:.3f}{lbl}")
        prev = lbl
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(steps),
          "-map", prev, "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])
    return out


def seam_report(chained: Path, link_frames: list[int], workdir: Path) -> list[dict]:
    """Measure each seam against the local adjacent-frame norm that precedes it."""
    frames_dir = workdir / "_seamframes"
    # Always re-extract. Caching these keyed only on "the directory is non-empty" would measure a
    # PREVIOUS chain's frames whenever the same workdir is reused with regenerated links — which is
    # exactly what a resumed run does.
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(chained),
          str(frames_dir / "f%05d.png")])

    def f(i: int) -> Path:                               # 1-indexed, as ffmpeg writes them
        return frames_dir / f"f{i:05d}.png"

    reports, boundary = [], 0
    for idx, n in enumerate(link_frames[:-1]):
        boundary += n                                    # last frame of link `idx` is #boundary
        lo = max(1, boundary - SEAM_WINDOW)
        window = [ssim(f(i), f(i + 1)) for i in range(lo, boundary)]
        norm = sum(window) / len(window)
        seam = ssim(f(boundary), f(boundary + 1))

        # Acuity continuity: does the next link start visibly crisper than this one ended?
        acu_window = [acuity(f(i)) for i in range(lo, boundary + 1)]
        acu_norm = sum(acu_window) / len(acu_window)
        acu_after = acuity(f(boundary + 1))
        acu_step = (acu_after - acu_norm) / acu_norm

        reports.append({"seam": idx + 1, "at_frame": boundary, "seam_ssim": round(seam, 4),
                        "local_norm": round(norm, 4), "gap": round(norm - seam, 4),
                        "ssim_pass": (norm - seam) <= SEAM_TOLERANCE,
                        "acuity_before": round(acu_norm, 3), "acuity_after": round(acu_after, 3),
                        "acuity_step": round(acu_step, 4),
                        "acuity_pass": abs(acu_step) <= ACUITY_TOLERANCE,
                        "pass": (norm - seam) <= SEAM_TOLERANCE
                                and abs(acu_step) <= ACUITY_TOLERANCE})
    return reports


def build(server: str, image: Path, prompts: list[str], links: int, out_stem: Path, *,
          width: int, height: int, frames: int, fps: int, seed: int, crossfade: float,
          denoise: bool, grade: bool = False, sharpen: bool = False) -> dict:
    work = out_stem.parent / f"{out_stem.name}_links"
    work.mkdir(parents=True, exist_ok=True)
    assert_opaque_rgb(image)

    start, produced, reused = image, [], 0
    for i in range(links):
        link_path = work / f"link{i + 1:02d}.mp4"
        if link_path.is_file():                          # resume: never regenerate a finished link
            print(f"[link {i+1}/{links}] reusing {link_path.name}", flush=True)
            produced.append(link_path)
            reused += 1
        else:
            prompt = prompts[i] if i < len(prompts) else prompts[-1]
            print(f"[link {i+1}/{links}] generating from {start.name} ...", flush=True)
            up = gc.upload_image(server, start)
            graph = gc.build_graph(up, prompt, width=width, height=height, frames=frames, fps=fps,
                                   seed=seed + i, use_lora=True, steps=4, cfg=1.0, shift=5.0,
                                   sampler="euler", scheduler="simple",
                                   prefix=f"asset_harness/chain_{out_stem.name}_{i+1:02d}")
            got = comfy_client.run_job(server, graph, work / f"link{i + 1:02d}",
                                       kinds=("videos", "gifs", "images"),
                                       label=f"{out_stem.name}-{i+1}")[0]
            if got != link_path:
                got.replace(link_path)
            produced.append(link_path)
        if i < links - 1:                                # prepare the next link's start frame
            raw = work / f"seam{i + 1:02d}_raw.png"
            start = clean_frame(last_frame(link_path, raw), work / f"seam{i + 1:02d}_clean.png",
                                denoise=denoise, grade=grade, sharpen=sharpen)

    final = out_stem.with_suffix(".mp4")
    concat(produced, final, crossfade=crossfade, fps=fps)
    counts = [probe(p)["frames"] for p in produced]
    total = probe(final)
    seams = seam_report(final, counts, work) if crossfade <= 0 else []
    return {"output": str(final), "links": len(produced), "reused_links": reused,
            "link_frames": counts, "total_frames": total["frames"],
            "expected_frames": sum(counts) if crossfade <= 0 else None,
            "resolution": f"{total['width']}x{total['height']}", "crossfade": crossfade,
            "cleanup_chain": cleanup_chain(denoise, grade, sharpen), "seams": seams}


def check_mmap(server: str) -> None:
    host = server.split("//")[-1].split(":")[0]
    r = subprocess.run(["ssh", host, "systemctl show comfyui.service -p ExecStart"],
                       capture_output=True, text=True)
    if r.returncode == 0 and "--disable-mmap" not in r.stdout:
        print(f"WARNING: {host} ComfyUI is running WITHOUT --disable-mmap. Every checkpoint load will "
              f"stall (~36 min instead of ~6 s) — a multi-link chain will take hours. See WI 1161.",
              file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8188")
    ap.add_argument("--image", required=True, type=Path, help="start still (opaque RGB)")
    ap.add_argument("--prompt", action="append", required=True,
                    help="motion prompt; repeat for per-link prompts (last one repeats)")
    ap.add_argument("--links", type=int, default=2)
    ap.add_argument("--out", required=True, type=Path, help="output path stem")
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--frames", type=int, default=97, help="97 @ 16fps = ~6.06s")
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--seed", type=int, default=901, help="link i uses seed+i")
    ap.add_argument("--crossfade", type=float, default=0.0,
                    help="seconds of crossfade per seam (default 0 = plain concat)")
    ap.add_argument("--no-denoise", dest="denoise", action="store_false",
                    help="drop hqdn3d from the cleanup chain (measured inert on a single frame)")
    ap.add_argument("--sharpen", action="store_true",
                    help="add the July unsharp to the cleanup. OFF by default: it COMPOUNDS across "
                         "seams (+83%% acuity per application; a 3-link chain measured +25%%/seam)")
    ap.add_argument("--grade", action="store_true",
                    help="add the July eq grade to the cleanup. OFF by default: it is applied once per "
                         "seam and COMPOUNDS (a 3-link chain measured +9.6%% saturation)")
    a = ap.parse_args()

    check_mmap(a.server)
    res = build(a.server, a.image, a.prompt, a.links, a.out, width=a.width, height=a.height,
                frames=a.frames, fps=a.fps, seed=a.seed, crossfade=a.crossfade, denoise=a.denoise,
                grade=a.grade, sharpen=a.sharpen)
    a.out.with_suffix(".chain.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    bad = [s for s in res["seams"] if not s["pass"]]
    if bad:
        def why(s: dict) -> str:
            parts = []
            if not s["ssim_pass"]:
                parts.append(f"continuity {s['seam_ssim']} vs norm {s['local_norm']} "
                             f"(gap {s['gap']} > {SEAM_TOLERANCE})")
            if not s["acuity_pass"]:
                parts.append(f"acuity step {s['acuity_step']:+.1%} "
                             f"({s['acuity_before']} -> {s['acuity_after']}, "
                             f"limit ±{ACUITY_TOLERANCE:.0%})")
            return f"seam {s['seam']} at frame {s['at_frame']}: " + " and ".join(parts)

        print(f"\nSEAM GATE FAILED on {len(bad)} seam(s): " + "; ".join(why(s) for s in bad),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
