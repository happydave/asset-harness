#!/usr/bin/env python3
"""WI 1046: objective audio QC meter -- pure DSP, no models, fully deterministic.

Built to turn the owner's WI 1043 ear notes into numbers. Their words -> what is measured here:

    "too hot"           -> sample peak, TRUE peak (4x oversampled), clipped-sample count + longest run
    "over compressed"   -> PLR (true peak - integrated LUFS) and crest factor
    "static popping"    -> click detection via sample-difference outliers
    "tinny"             -> spectral tilt, centroid, band-energy ratios
    perceived level     -> integrated + short-term LUFS (ITU-R BS.1770-4)

Why this exists alongside the learned scorers: CLIP/PickScore are image models, CLAP measures genre-tag
match, and Audiobox returns a learned aesthetic OPINION. None of them can tell you the signal is
clipping. This measures physics, so it is a candidate GATE (deterministic, zero owner time) rather than
a selector.

Loudness is implemented from the standard rather than pulled in as a dependency: BS.1770-4 is a
high-shelf biquad + an RLB high-pass, then mean-square over 400 ms blocks at 75 % overlap with a -70 LUFS
absolute gate and a -10 LU relative gate. Coefficients below are the standard's 48 kHz values, so input
is resampled to 48 kHz before weighting.

THRESHOLDS ARE ADVISORY, NOT A GATE THE OWNER SET. Each carries its origin in ADVISORY below; they exist
to draw the eye, not to pass/fail a track.

    scoring/.venv/bin/python scoring/audio_qc.py <dir-or-files...> [-o out.json] [--windows]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

TARGET_SR = 48000
BLOCK_S, OVERLAP = 0.400, 0.75          # BS.1770-4 gating block + overlap
ABS_GATE_LUFS, REL_GATE_LU = -70.0, -10.0
SHORT_TERM_S = 3.0                      # BS.1770-4 short-term window
CLIP_CEIL = 0.9995                      # |x| at/above this counts as full-scale
CLIP_RUN = 3                            # consecutive full-scale samples = a flat top, not a lucky peak
WINDOW_S = 1.0                          # timeline resolution

# BS.1770-4 K-weighting, 48 kHz (Tables 1 & 2 of the recommendation)
_SHELF_B = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_SHELF_A = np.array([1.0, -1.69065929318241, 0.73248077421585])
_RLB_B = np.array([1.0, -2.0, 1.0])
_RLB_A = np.array([1.0, -1.99004745483398, 0.99007225036621])

ADVISORY = {
    # EBU R128 / ITU-R BS.1770 delivery practice: -1 dBTP ceiling to survive lossy encoding.
    "true_peak_dbtp": (-1.0, 0.0, "EBU R128 delivery ceiling -1 dBTP; >0 dBTP is an over"),
    # Any sustained flat top is digital clipping; there is no benign amount.
    "clipped_pct": (0.001, 0.01, "any sustained full-scale run is clipping; 0 is the only clean value"),
    # PLR (peak-to-loudness): contemporary loud masters sit ~8; <6 is heavily limited. Convention,
    # not a standard -- treat as a smell, not a defect.
    "plr_db": (8.0, 6.0, "convention: pop masters ~8-12 PLR; <6 reads as brickwalled (NOT a standard)"),
}


def _resample(y: np.ndarray, sr: int, target: int = TARGET_SR) -> np.ndarray:
    if sr == target:
        return y
    g = np.gcd(int(sr), int(target))
    return signal.resample_poly(y, target // g, sr // g).astype(np.float64)


def k_weight(y: np.ndarray) -> np.ndarray:
    """BS.1770-4 K-weighting: high-shelf then RLB high-pass. Input must be 48 kHz."""
    return signal.lfilter(_RLB_B, _RLB_A, signal.lfilter(_SHELF_B, _SHELF_A, y))


def _block_loudness(y48: np.ndarray) -> np.ndarray:
    """Per-block loudness (LKFS) over 400 ms blocks at 75 % overlap. Mono: channel gain G = 1.0."""
    yk = k_weight(y48)
    n = int(BLOCK_S * TARGET_SR)
    step = max(1, int(n * (1.0 - OVERLAP)))
    if len(yk) < n:
        return np.array([])
    starts = range(0, len(yk) - n + 1, step)
    ms = np.array([np.mean(yk[s:s + n] ** 2) for s in starts])
    with np.errstate(divide="ignore"):
        return -0.691 + 10.0 * np.log10(np.maximum(ms, 1e-30))


def integrated_lufs(y48: np.ndarray) -> float:
    """Gated integrated loudness. Two-stage gate per BS.1770-4."""
    lj = _block_loudness(y48)
    if lj.size == 0:
        return float("nan")
    yk = k_weight(y48)
    n = int(BLOCK_S * TARGET_SR)
    step = max(1, int(n * (1.0 - OVERLAP)))
    ms = np.array([np.mean(yk[s:s + n] ** 2) for s in range(0, len(yk) - n + 1, step)])

    keep = lj > ABS_GATE_LUFS                                    # absolute gate
    if not keep.any():
        return float("nan")
    ungated = -0.691 + 10.0 * np.log10(max(ms[keep].mean(), 1e-30))
    keep &= lj > (ungated + REL_GATE_LU)                          # relative gate
    if not keep.any():
        return float("nan")
    return float(-0.691 + 10.0 * np.log10(max(ms[keep].mean(), 1e-30)))


def short_term_max_lufs(y48: np.ndarray) -> float:
    n = int(SHORT_TERM_S * TARGET_SR)
    if len(y48) < n:
        return float("nan")
    yk = k_weight(y48)
    step = int(TARGET_SR * 0.1)
    vals = [-0.691 + 10.0 * np.log10(max(np.mean(yk[s:s + n] ** 2), 1e-30))
            for s in range(0, len(yk) - n + 1, step)]
    return float(max(vals))


def true_peak_dbtp(y: np.ndarray, sr: int) -> float:
    """4x-oversampled peak -- catches inter-sample peaks a raw max() misses (BS.1770-4 Annex 2)."""
    up = signal.resample_poly(y, 4, 1)
    return float(20.0 * np.log10(max(np.max(np.abs(up)), 1e-12)))


def _dbfs(x: float) -> float:
    return float(20.0 * np.log10(max(abs(x), 1e-12)))


def clipping(y: np.ndarray) -> dict:
    """Full-scale samples and, more tellingly, RUNS of them (a flat top is clipping; one sample is not)."""
    at = np.abs(y) >= CLIP_CEIL
    total = int(at.sum())
    runs, longest, cur = 0, 0, 0
    for v in at:
        if v:
            cur += 1
        else:
            if cur >= CLIP_RUN:
                runs += 1
            longest = max(longest, cur)
            cur = 0
    if cur >= CLIP_RUN:
        runs += 1
    longest = max(longest, cur)
    return {"clipped_samples": total,
            "clipped_pct": round(100.0 * total / max(len(y), 1), 5),
            "clip_runs": runs, "longest_clip_run": int(longest)}


def clicks_naive(y: np.ndarray, sr: int) -> dict:
    """SUPERSEDED by clicks(). Kept so the improvement stays measurable rather than asserted.

    Second-difference outliers. The flaw found in WI 1046: a drum hit is also a large second
    difference, so this fires on legitimate percussive transients -- it reported 350 clicks on a track
    the owner heard no popping in. Honest as "count of large discontinuities", useless as "audible pops".
    """
    d2 = np.diff(y, n=2)
    mad = np.median(np.abs(d2 - np.median(d2)))
    if mad <= 0:
        return {"clicks_naive": 0}
    thresh = 20.0 * 1.4826 * mad
    idx = np.flatnonzero(np.abs(d2) > thresh)
    n = 0 if idx.size == 0 else 1 + int(np.count_nonzero(np.diff(idx) > sr * 0.005))
    return {"clicks_naive": n}


def clicks(y: np.ndarray, sr: int) -> dict:
    """Impulsive artifacts ('static popping'), separated from musical percussion.

    The discriminator: a drum hit is BAND-LIMITED -- its energy is concentrated well below Nyquist and
    it carries a matching low-frequency thump. A digital click is a true discontinuity, so its energy
    extends to the top of the spectrum and it has NO low-frequency partner. So:

      1. high-pass at 12 kHz -- above most musical transient energy, below Nyquist;
      2. find envelope peaks that stand far above the LOCAL robust background (MAD), not a global one,
         so a quiet passage and a loud chorus are judged on their own terms;
      3. REJECT any candidate whose low band (<1 kHz) rises at the same instant -- that is a drum,
         not a click. This is the step the naive detector lacked.
    """
    if len(y) < sr // 10:
        return {"click_count": 0, "click_rate_per_min": 0.0}
    nyq = sr / 2.0
    # 18 kHz, not 12 kHz: cymbals and snare noise still carry real energy at 12 kHz, so that band cannot
    # separate percussion from a discontinuity. The top octave is where music is near-empty and a true
    # sample-level discontinuity is not.
    hp_hz = min(18000.0, 0.9 * nyq)
    bh, ah = signal.butter(4, hp_hz / nyq, btype="high")
    bl, al = signal.butter(4, min(1000.0, 0.5 * nyq) / nyq, btype="low")
    hi = np.abs(signal.lfilter(bh, ah, y))
    lo = np.abs(signal.lfilter(bl, al, y))

    win = max(1, int(sr * 0.001))                     # ~1 ms envelope
    k = np.ones(win) / win
    hi_env = np.convolve(hi, k, mode="same")
    lo_env = np.convolve(lo, k, mode="same")

    # local background over ~200 ms, robust to the transients we are hunting
    blk = max(1, int(sr * 0.2))
    n_blk = max(1, len(hi_env) // blk)
    bg = np.repeat([np.median(hi_env[i * blk:(i + 1) * blk]) or 1e-12 for i in range(n_blk)], blk)
    bg = np.resize(bg, len(hi_env))
    lo_bg = np.repeat([np.median(lo_env[i * blk:(i + 1) * blk]) or 1e-12 for i in range(n_blk)], blk)
    lo_bg = np.resize(lo_bg, len(lo_env))

    # An ABSOLUTE floor as well as the relative one. Without it, a clean band-limited signal has a
    # top-octave background of ~0, so "12x the background" is satisfied by numerical noise and filter
    # start-up transients -- which is why the first version of this fired on a pure sine wave.
    rms = float(np.sqrt(np.mean(y ** 2))) + 1e-12
    floor = 0.02 * rms
    cand = np.flatnonzero((hi_env > 12.0 * bg) & (hi_env > floor))
    if cand.size == 0:
        return {"click_count": 0, "click_rate_per_min": 0.0}
    # collapse to events (one pop spans many samples)
    events = np.split(cand, 1 + np.flatnonzero(np.diff(cand) > sr * 0.005))
    kept = 0
    for ev in events:
        i = ev[int(np.argmax(hi_env[ev]))]
        # a drum hit lifts the low band too; a click does not
        if lo_env[i] < 6.0 * lo_bg[i]:
            kept += 1
    return {"click_count": int(kept),
            "click_rate_per_min": round(kept / (len(y) / sr / 60.0), 2)}


def spectral(y48: np.ndarray) -> dict:
    """Tilt / centroid / band ratios -- the 'tinny' axis (thin, HF-heavy, missing low-mid body)."""
    f, p = signal.welch(y48, fs=TARGET_SR, nperseg=8192)
    tot = p.sum() + 1e-30

    def band(lo, hi):
        return float(p[(f >= lo) & (f < hi)].sum() / tot)
    low, lowmid, mid, hi = band(20, 200), band(200, 2000), band(2000, 4000), band(4000, 20000)
    centroid = float((f * p).sum() / tot)
    return {"centroid_hz": round(centroid, 1),
            "band_low_20_200": round(low, 4), "band_lowmid_200_2k": round(lowmid, 4),
            "band_mid_2k_4k": round(mid, 4), "band_hi_4k_20k": round(hi, 4),
            # >1 means more energy above 4 kHz than in the 200 Hz-2 kHz body: the 'tinny' direction
            "hf_to_body_ratio": round(hi / max(lowmid, 1e-9), 4)}


def truncation(y: np.ndarray, sr: int) -> dict:
    """Detect a track cut off mid-phrase rather than allowed to resolve (the WI 1043 turbo_703 defect).

    A natural ending DECAYS -- an outro, a release, a fade -- so the level slides from full to silence
    over a while. A truncation CLIFFS: the track is at near-full level and then stops within a couple
    hundred ms. So the signature is: the level shortly before the end is still close to the track's own
    median, and it collapses to silence abruptly. Both conditions are relative to the track's own level,
    so this makes no assumption about genre or absolute loudness.
    """
    hop = int(0.05 * sr)                                   # 50 ms envelope
    if hop <= 0 or len(y) < sr:
        return {"truncated": False, "end_decay_s": None}
    env = np.array([np.sqrt(np.mean(y[i:i + hop] ** 2)) for i in range(0, len(y) - hop, hop)])
    db = 20.0 * np.log10(np.maximum(env, 1e-12))
    med = float(np.median(db[db > -60.0])) if np.any(db > -60.0) else -60.0
    SIL = -45.0                                            # below this = effectively silent
    active = np.flatnonzero(db > SIL)
    if active.size == 0:
        return {"truncated": False, "end_decay_s": None}
    end = active[-1]                                       # last non-silent frame
    # walk back to the last frame that was within 6 dB of the track's median level
    sustain = end
    while sustain > 0 and db[sustain] < med - 6.0:
        sustain -= 1
    decay_s = (end - sustain) * hop / sr
    # Truncated = the track was at near-median level and then collapsed to silence within < 0.3 s (a
    # cliff), close to the file end. A natural outro/release/fade takes longer (measured: 0.5-1.3 s on
    # the WI 1043 set; the one truncated track cliffed in 0.05 s). db[sustain] >= med-6 holds by
    # construction of `sustain`, so the discriminator is the decay TIME, not the end level -- the last
    # audible frame is itself mid-collapse and sits well below median, so it must not be gated on.
    trailing_sil_s = (len(env) - 1 - end) * hop / sr
    truncated = bool(decay_s < 0.30 and db[sustain] >= med - 6.0 and trailing_sil_s < 2.5)
    return {"truncated": truncated, "end_decay_s": round(decay_s, 3),
            "end_level_vs_median_db": round(float(db[end] - med), 1)}


def timeline(y: np.ndarray, sr: int) -> list:
    """Per-second peak / RMS / clipped count, so a report can point at WHERE a track goes hot."""
    n = int(WINDOW_S * sr)
    out = []
    for i, s in enumerate(range(0, len(y), n)):
        w = y[s:s + n]
        if len(w) < sr * 0.1:
            continue
        out.append({"t": i * WINDOW_S,
                    "peak_dbfs": round(_dbfs(np.max(np.abs(w))), 2),
                    "rms_dbfs": round(_dbfs(np.sqrt(np.mean(w ** 2))), 2),
                    "clipped": int((np.abs(w) >= CLIP_CEIL).sum())})
    return out


def analyse(path: Path, want_windows: bool = False) -> dict:
    y, sr = sf.read(str(path), dtype="float64", always_2d=True)
    channels = y.shape[1]
    mono = y.mean(axis=1)
    y48 = _resample(mono, sr)

    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono ** 2)))
    tp = true_peak_dbtp(mono, sr)
    lufs = integrated_lufs(y48)
    rec = {
        "file": path.name, "sr": sr, "channels": channels,
        "duration_s": round(len(mono) / sr, 3),
        "sample_peak_dbfs": round(_dbfs(peak), 2),
        "true_peak_dbtp": round(tp, 2),
        "rms_dbfs": round(_dbfs(rms), 2),
        "dc_offset": round(float(np.mean(mono)), 6),
        "lufs_integrated": None if np.isnan(lufs) else round(lufs, 2),
        "lufs_short_term_max": round(short_term_max_lufs(y48), 2),
        "crest_factor_db": round(_dbfs(peak) - _dbfs(rms), 2),
        "plr_db": None if np.isnan(lufs) else round(tp - lufs, 2),
    }
    rec.update(clipping(mono))
    rec.update(clicks(mono, sr))
    rec.update(clicks_naive(mono, sr))  # retained so the WI 1046 improvement stays measurable
    rec.update(truncation(mono, sr))
    rec.update(spectral(y48))
    if want_windows:
        rec["windows"] = timeline(mono, sr)
    rec["flags"] = flags(rec)
    return rec


def flags(rec: dict) -> list:
    """Advisory only. Each references its origin in ADVISORY; none is a bar the owner set."""
    out = []
    for metric, (warn, fail, _why) in ADVISORY.items():
        v = rec.get(metric)
        if v is None:
            continue
        worse_is_higher = metric != "plr_db"
        if worse_is_higher:
            if v > fail:
                out.append(f"FAIL {metric}={v}")
            elif v > warn:
                out.append(f"WARN {metric}={v}")
        else:
            if v < fail:
                out.append(f"FAIL {metric}={v}")
            elif v < warn:
                out.append(f"WARN {metric}={v}")
    if rec.get("longest_clip_run", 0) >= CLIP_RUN:
        out.append(f"FAIL flat-top run={rec['longest_clip_run']} samples")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="audio files, or directories to scan for flac/wav")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--windows", action="store_true", help="include the per-second timeline")
    args = ap.parse_args()

    files = []
    for p in map(Path, args.paths):
        if p.is_dir():
            files += sorted([q for ext in ("*.flac", "*.wav") for q in p.glob(ext)])
        elif p.exists():
            files.append(p)
    if not files:
        raise SystemExit("no audio files found")

    recs = [analyse(f, args.windows) for f in files]
    print(f"{'file':22s} {'peak':>7s} {'truePk':>7s} {'LUFS':>7s} {'PLR':>6s} "
          f"{'clip%':>7s} {'run':>4s} {'clicks':>6s} {'HF/body':>8s}  flags")
    for r in recs:
        print(f"{r['file'][:22]:22s} {r['sample_peak_dbfs']:7.2f} {r['true_peak_dbtp']:7.2f} "
              f"{(r['lufs_integrated'] or float('nan')):7.2f} {(r['plr_db'] or float('nan')):6.2f} "
              f"{r['clipped_pct']:7.4f} {r['longest_clip_run']:4d} {r['click_count']:6d} "
              f"{r['hf_to_body_ratio']:8.3f}  {'; '.join(r['flags'])}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"advisory": {k: {"warn": w, "fail": f, "origin": o} for k, (w, f, o) in ADVISORY.items()},
             "tracks": recs}, indent=2))
        print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
