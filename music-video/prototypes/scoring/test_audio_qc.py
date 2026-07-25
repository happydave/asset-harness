#!/usr/bin/env python3
"""WI 1046: validate audio_qc.py against synthesised known signals and an INDEPENDENT implementation.

A metric you wrote, validated only against itself, tells you nothing. So:
  * loudness is cross-checked against ffmpeg's `ebur128` filter -- a separate, widely-used BS.1770
    implementation that shares no code with ours;
  * clipping / true-peak / clicks are checked against signals whose defects are known BY CONSTRUCTION;
  * scaling is checked for exact dB linearity, which catches an error the absolute anchors would miss.

Run: scoring/.venv/bin/python scoring/test_audio_qc.py   (exit 0 = all pass)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_qc as qc

SR = 48000
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}")
    if not ok:
        FAILS.append(name)


def close(a: float, b: float, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def write(y: np.ndarray, path: Path, sr: int = SR) -> Path:
    sf.write(str(path), y, sr, subtype="PCM_24")
    return path


def sine(freq: float, secs: float, amp: float, sr: int = SR) -> np.ndarray:
    t = np.arange(int(secs * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def ffmpeg_lufs(path: Path) -> float | None:
    """Integrated loudness from ffmpeg's ebur128 -- the independent reference."""
    try:
        p = subprocess.run(["ffmpeg", "-nostdin", "-i", str(path), "-filter:a", "ebur128",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.findall(r"I:\s*(-?\d+\.\d+)\s*LUFS", p.stderr)
    return float(m[-1]) if m else None


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="audioqc_"))

    print("K-weighting filter shape (must match BS.1770-4's documented response):")
    w, h = signal.freqz(np.convolve(qc._SHELF_B, qc._RLB_B),
                        np.convolve(qc._SHELF_A, qc._RLB_A), worN=8192, fs=SR)
    db = 20 * np.log10(np.abs(h) + 1e-30)

    def at(f):
        return float(db[np.argmin(np.abs(w - f))])
    # Expected values are BS.1770-4's documented K-weighting curve. Note the unity point is ~500 Hz,
    # NOT 1 kHz -- the high-shelf has already begun to rise by 1 kHz (+0.7 dB), and the RLB high-pass is
    # a gentle 2nd-order (-5.6 dB at 40 Hz, -13.2 dB at 20 Hz), not a steep one.
    check("high-shelf plateau ~ +4 dB at 10 kHz", close(at(10000), 4.04, 0.15), f"{at(10000):+.2f} dB")
    check("unity ~ 0 dB at 500 Hz", close(at(500), 0.0, 0.15), f"{at(500):+.2f} dB")
    check("shelf rising by 1 kHz (+0.7 dB)", close(at(1000), 0.70, 0.15), f"{at(1000):+.2f} dB")
    check("shelf fully in by 4 kHz (+4 dB)", close(at(4000), 3.97, 0.20), f"{at(4000):+.2f} dB")
    check("RLB: -5.6 dB at 40 Hz", close(at(40), -5.58, 0.30), f"{at(40):+.2f} dB")
    check("RLB: -13.2 dB at 20 Hz", close(at(20), -13.18, 0.40), f"{at(20):+.2f} dB")

    print("\nLoudness vs ffmpeg ebur128 (independent BS.1770 implementation):")
    cases = {"sine1k_-20dBFS": sine(1000, 12, 10 ** (-20 / 20)),
             "sine1k_-6dBFS": sine(1000, 12, 10 ** (-6 / 20)),
             "pinkish_noise": None}
    rng = np.random.default_rng(1046)
    white = rng.standard_normal(SR * 12)
    b, a = signal.butter(1, 500 / (SR / 2), btype="low")
    cases["pinkish_noise"] = 0.1 * signal.lfilter(b, a, white) / np.max(np.abs(signal.lfilter(b, a, white)))

    any_ref = False
    for name, y in cases.items():
        p = write(y, tmp / f"{name}.wav")
        mine = qc.integrated_lufs(qc._resample(y, SR))
        ref = ffmpeg_lufs(p)
        if ref is None:
            check(f"{name} (ffmpeg unavailable -- reference skipped)", True, "")
            continue
        any_ref = True
        check(f"{name} within 0.5 LU of ebur128", close(mine, ref, 0.5),
              f"ours {mine:.2f} vs ffmpeg {ref:.2f} LUFS")
    if not any_ref:
        check("an independent loudness reference was available", False,
              "ffmpeg ebur128 produced no reading -- loudness is UNVALIDATED")

    print("\nScaling linearity (halving amplitude must be exactly -6.02 LU):")
    loud = qc.integrated_lufs(sine(1000, 12, 0.5))
    quiet = qc.integrated_lufs(sine(1000, 12, 0.25))
    check("-6.02 LU for a 2x amplitude drop", close(loud - quiet, 6.02, 0.05),
          f"delta {loud - quiet:.3f} LU")

    print("\nClipping detection (known-bad vs known-good by construction):")
    clean = sine(1000, 5, 0.5)
    clipped = np.clip(sine(1000, 5, 1.6), -1.0, 1.0)   # hard-clipped: long flat tops
    c_clean, c_bad = qc.clipping(clean), qc.clipping(clipped)
    check("clean sine reports zero clipping", c_clean["clipped_samples"] == 0,
          f"{c_clean}")
    check("hard-clipped sine is detected", c_bad["clipped_pct"] > 1.0 and c_bad["longest_clip_run"] >= 3,
          f"pct={c_bad['clipped_pct']} longest_run={c_bad['longest_clip_run']}")
    check("clipped sine raises a FAIL flag",
          any(f.startswith("FAIL") for f in qc.flags({**c_bad, "true_peak_dbtp": 0.0, "plr_db": 9.0})))

    print("\nTrue peak (must catch an inter-sample peak a raw max() misses):")
    # a sine placed between sample instants: raw samples understate the real analogue peak
    t = np.arange(int(0.5 * SR)) / SR
    inter = 0.99 * np.sin(2 * np.pi * (SR / 4) * t + np.pi / 4)
    raw = 20 * np.log10(np.max(np.abs(inter)))
    tp = qc.true_peak_dbtp(inter, SR)
    check("true peak >= sample peak", tp >= raw - 1e-6, f"true {tp:.2f} vs sample {raw:.2f} dB")
    check("inter-sample peak exceeds sample peak", tp > raw + 0.1, f"+{tp - raw:.2f} dB recovered")

    print("\nClick detection (impulses inserted at known positions):")
    y = sine(440, 5, 0.3).copy()
    for pos in (int(0.5 * SR), int(1.5 * SR), int(3.2 * SR)):
        y[pos] = 0.95
    got = qc.clicks(y, SR)["click_count"]
    check("3 inserted clicks detected", got == 3, f"found {got}")
    check("clean tone reports no clicks", qc.clicks(sine(440, 5, 0.3), SR)["click_count"] == 0)

    print("\nClicks vs DRUMS -- the failure that motivated the rewrite:")
    # Band-limited percussive hits: fast attack, exponential decay, energy concentrated low/mid -- i.e.
    # a drum. It is a huge second difference, which is exactly why the naive detector fired on it.
    def drums(n_hits: int, secs: float = 6.0) -> np.ndarray:
        out = np.zeros(int(secs * SR))
        bd, ad = signal.butter(4, [60 / (SR / 2), 4000 / (SR / 2)], btype="band")
        for i in range(n_hits):
            s = int((0.3 + i * (secs - 0.6) / max(n_hits - 1, 1)) * SR)
            ln = int(0.12 * SR)
            hit = signal.lfilter(bd, ad, rng.standard_normal(ln))
            hit *= np.exp(-np.linspace(0, 9, ln)) * 0.7 / (np.max(np.abs(hit)) + 1e-12)
            out[s:s + ln] += hit[:len(out) - s]
        return out

    only_drums = drums(12) + sine(220, 6, 0.15)
    naive_on_drums = qc.clicks_naive(only_drums, SR)["clicks_naive"]
    new_on_drums = qc.clicks(only_drums, SR)["click_count"]
    check("NEW detector does not fire on drums", new_on_drums <= 1,
          f"new={new_on_drums} vs naive={naive_on_drums}")
    check("the naive detector DID fire on drums (regression is real)", naive_on_drums >= 3,
          f"naive={naive_on_drums}")

    drums_plus = only_drums.copy()
    for pos in (int(1.1 * SR), int(2.7 * SR), int(4.4 * SR), int(5.2 * SR)):
        drums_plus[pos] += 0.9
    found = qc.clicks(drums_plus, SR)["click_count"]
    check("4 clicks still found amid drums", 3 <= found <= 6, f"found {found}")
    check("clicks-amid-drums exceeds drums-alone", found > new_on_drums,
          f"{found} > {new_on_drums}")

    print("\nSpectral tilt ('tinny' axis must order known spectra correctly):")
    # Band-limited NOISE, not pure tones: tones leave one band at literally zero energy, which makes the
    # ratio degenerate (1e9 vs 0) and tests ordering only trivially. Noise gives realistic magnitudes.
    nz = rng.standard_normal(SR * 6)
    bb, ab = signal.butter(4, [200 / (SR / 2), 2000 / (SR / 2)], btype="band")
    bh, ah = signal.butter(4, 4000 / (SR / 2), btype="high")
    body = 0.3 * signal.lfilter(bb, ab, nz)
    tinny = 0.3 * signal.lfilter(bh, ah, nz)
    both = body + tinny
    rb = qc.spectral(body)["hf_to_body_ratio"]
    rt = qc.spectral(tinny)["hf_to_body_ratio"]
    rm = qc.spectral(both)["hf_to_body_ratio"]
    check("HF-heavy noise ranks as more tinny than body-heavy", rt > rb,
          f"tinny {rt:.3f} > body {rb:.3f}")
    check("a balanced mix falls between the two", rb < rm < rt, f"body {rb:.3f} < mix {rm:.3f} < {rt:.3f}")
    check("body-heavy noise reads below 1.0 (more body than HF)", rb < 1.0, f"{rb:.3f}")

    print("\nDeterminism (same file twice -> identical metrics):")
    p = write(sine(1000, 6, 0.4), tmp / "det.wav")
    a1, a2 = qc.analyse(p), qc.analyse(p)
    check("analyse() is deterministic", a1 == a2)

    print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
