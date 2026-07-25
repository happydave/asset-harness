#!/usr/bin/env python3
"""WI 1046: gain-stage a set of songs -- loudness-match and/or enforce a true-peak ceiling.

PURE GAIN ONLY. No limiting, no compression, no clipping. Every sample is multiplied by one constant
per file, so the waveform shape is untouched and the operation is exactly invertible. That matters for
both uses:

  * DELIVERY -- no candidate should ever ship above the -1 dBTP ceiling (EBU R128 practice). WI 1046
    measured all four WI 1043 turbo tracks over 0 dBTP; a ~1 dB trim clears them completely, because the
    defect was headroom, not dynamics (their PLR was HIGHER than base's).
  * FAIR A/B -- a blind listening test must be loudness-matched or it measures level, not quality:
    louder reliably reads as "better". The WI 1043 test was not matched (a 1.5 LU spread), so its
    re-test must be.

Matching strategy, chosen so no file is ever boosted into a limiter:
  1. target = the QUIETEST integrated LUFS in the set, so every gain is <= 0 dB;
  2. per-file gain = target - its LUFS;
  3. if any resulting true peak still exceeds the ceiling, trim the WHOLE SET by the same extra amount --
     never per-file, which would silently un-match the loudness the step above just established.

    scoring/.venv/bin/python scoring/master.py <dir-or-files...> -o <out-dir> [--ceiling -1.0] [--no-match]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_qc as qc

DEFAULT_CEILING = -1.0  # dBTP, EBU R128 delivery practice


def _apply_gain(src: Path, dst: Path, gain_db: float) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src),
                    "-af", f"volume={gain_db:.4f}dB", "-c:a", "flac", str(dst)], check=True)


def apply_ceiling(src: Path, ceiling: float = DEFAULT_CEILING, dst: Path | None = None) -> dict:
    """Trim ONE file with pure gain so its true peak sits at/below `ceiling` dBTP. No limiting.

    A no-op if the track is already under the ceiling (never boosts a quiet track up to it). In-place
    when `dst` is None (writes a temp sibling, then atomically replaces). Returns the before/after true
    peaks and the gain applied -- the single-file counterpart to the set-wide plan_gains().
    """
    src = Path(src)
    before = qc.analyse(src)["true_peak_dbtp"]
    gain = min(0.0, ceiling - before)          # <= 0: only ever trims, never boosts
    if gain == 0.0 and dst is None:
        return {"applied_gain_db": 0.0, "before_dbtp": before, "after_dbtp": before, "changed": False}
    # temp keeps the real extension LAST so ffmpeg can infer the output format (a ".ceil.tmp" suffix
    # leaves it unable to choose a muxer)
    out = Path(dst) if dst is not None else src.with_name(f"{src.stem}.ceiltmp{src.suffix}")
    _apply_gain(src, out, gain)
    after = qc.analyse(out)["true_peak_dbtp"]
    if dst is None:
        out.replace(src)
    return {"applied_gain_db": round(gain, 4), "before_dbtp": before,
            "after_dbtp": after, "changed": gain != 0.0}


def plan_gains(measured: list[dict], *, match: bool, ceiling: float) -> tuple[dict, dict]:
    """-> ({file: gain_db}, info). Pure arithmetic on measurements; no I/O, so it is unit-testable."""
    info: dict = {"ceiling_dbtp": ceiling, "loudness_matched": match}
    gains: dict = {}

    if match:
        lufs = {m["file"]: m["lufs_integrated"] for m in measured if m.get("lufs_integrated") is not None}
        if not lufs:
            raise SystemExit("no integrated loudness available -- cannot loudness-match")
        target = min(lufs.values())          # quietest, so every gain is <= 0 dB (never boost into clipping)
        info["target_lufs"] = round(target, 2)
        gains = {f: target - v for f, v in lufs.items()}
    else:
        gains = {m["file"]: 0.0 for m in measured}

    # Resulting true peaks under the planned gains; a uniform extra trim preserves the match.
    peaks = {m["file"]: m["true_peak_dbtp"] + gains.get(m["file"], 0.0) for m in measured}
    over = max(peaks.values()) - ceiling
    info["set_trim_db"] = round(-over, 4) if over > 0 else 0.0
    if over > 0:
        gains = {f: g - over for f, g in gains.items()}
    info["gains_db"] = {f: round(g, 4) for f, g in gains.items()}
    return gains, info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--ceiling", type=float, default=DEFAULT_CEILING, help="true-peak ceiling in dBTP")
    ap.add_argument("--no-match", action="store_true", help="ceiling only; do not loudness-match")
    args = ap.parse_args()

    files: list[Path] = []
    for p in map(Path, args.paths):
        if p.is_dir():
            files += sorted(q for ext in ("*.flac", "*.wav") for q in p.glob(ext))
        elif p.exists():
            files.append(p)
    if not files:
        raise SystemExit("no audio files found")

    by_name = {f.name: f for f in files}
    measured = [qc.analyse(f) for f in files]
    gains, info = plan_gains(measured, match=not args.no_match, ceiling=args.ceiling)

    out_dir = Path(args.out)
    print(f"{'file':22s} {'gain':>7s}   {'LUFS':>16s}   {'true peak dBTP':>18s}   flags")
    after = []
    for m in measured:
        name = m["file"]
        _apply_gain(by_name[name], out_dir / name, gains[name])
        a = qc.analyse(out_dir / name)
        after.append(a)
        print(f"{name[:22]:22s} {gains[name]:+7.2f}   "
              f"{m['lufs_integrated']:7.2f} -> {a['lufs_integrated']:6.2f}   "
              f"{m['true_peak_dbtp']:+8.2f} -> {a['true_peak_dbtp']:+7.2f}   "
              f"{'; '.join(a['flags']) or 'CLEAN'}")

    lu = [a["lufs_integrated"] for a in after if a["lufs_integrated"] is not None]
    tp = [a["true_peak_dbtp"] for a in after]
    info["result"] = {"lufs_spread_lu": round(max(lu) - min(lu), 3) if lu else None,
                      "max_true_peak_dbtp": round(max(tp), 3),
                      "any_flags": any(a["flags"] for a in after)}
    (out_dir / "mastering.json").write_text(json.dumps(info, indent=2))
    print(f"\nloudness spread after: {info['result']['lufs_spread_lu']} LU   "
          f"max true peak: {info['result']['max_true_peak_dbtp']:+.2f} dBTP   "
          f"flags: {'NONE' if not info['result']['any_flags'] else 'PRESENT'}")
    print(f"-> {out_dir}/  (+ mastering.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
