#!/usr/bin/env python3
"""Shared ComfyUI client helpers for the music-video prototypes.

Robust job waiting — the rule learned the expensive way (WI 1013/1015/1018, which lost an overnight
batch to it):

  * Wait on the server's TERMINAL job state (`/history`), never a wall-clock cap that discards a
    finished job, and never a `pgrep` on a client process.
  * A job absent from `/history` is "still pending/running" -> keep waiting. It is a failure only if
    a caller-set `backstop` is exceeded (and even then the prompt_id + recovery command are surfaced,
    not discarded) or if it has truly vanished (absent from both `/history` and `/queue`).
  * A finished prompt's outputs are always recoverable after the fact via `fetch_from_history`.

Stdlib + requests only. Importable by the other clients here; copyable by other tracks.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import requests

DEFAULT_SERVER = "http://ai2:8188"
OUTPUT_KINDS = ("videos", "gifs", "images", "audio")


def queue(server: str, graph: dict, client_id: str | None = None) -> str:
    """Submit a graph; return its prompt_id. Raises on a rejected graph."""
    r = requests.post(f"{server.rstrip('/')}/prompt",
                      json={"prompt": graph, "client_id": client_id or uuid.uuid4().hex},
                      timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"/prompt rejected ({r.status_code}):\n{r.text}")
    return r.json()["prompt_id"]


def _get_json(server: str, path: str, *, timeout: float = 30, retries: int = 3):
    """GET + .json() with a few retries so a transient network blip doesn't abort a long wait."""
    last = None
    for _ in range(retries):
        try:
            return requests.get(f"{server.rstrip('/')}{path}", timeout=timeout).json()
        except requests.RequestException as e:
            last = e
            time.sleep(2)
    raise SystemExit(f"ComfyUI unreachable at {server}{path}: {last}")


def _queue_state(server: str, pid: str) -> str:
    """'running' / 'pending' / 'absent' / 'unknown' — best-effort, for heartbeat + vanished detection.

    ComfyUI /queue entries are [number, prompt_id, ...]; the pid is item[1]."""
    try:
        q = requests.get(f"{server.rstrip('/')}/queue", timeout=15).json()
    except requests.RequestException:
        return "unknown"
    for item in q.get("queue_running", []):
        if len(item) > 1 and item[1] == pid:
            return "running"
    for item in q.get("queue_pending", []):
        if len(item) > 1 and item[1] == pid:
            return "pending"
    return "absent"


def wait_for_history(server: str, pid: str, *, poll: float = 5.0, heartbeat: float = 120.0,
                     backstop: float | None = None, grace: float = 60.0, label: str = "") -> dict:
    """Block until `pid` reaches a terminal state in /history; return the history entry on success.

    - **No wall-clock cap by default** (`backstop=None`): a job merely still running is not a timeout.
    - Raises on server-side `error`, on an exceeded `backstop` (with a recovery hint, not discarding),
      and on a vanished job (absent from BOTH /history and /queue past `grace` — a submit failure, not
      a slow run; the one case where indefinite waiting must not apply).
    """
    server = server.rstrip("/")
    t0 = last_hb = time.time()
    absent_since: float | None = None
    tag = f"[{label}] " if label else ""
    while True:
        hist = _get_json(server, f"/history/{pid}")
        if pid in hist:
            status = hist[pid].get("status", {})
            if status.get("status_str") == "error":
                raise SystemExit(f"{tag}job {pid} failed on the server:\n{status}")
            return hist[pid]  # terminal + not error == done

        now = time.time()
        state = _queue_state(server, pid)
        if state == "absent":
            absent_since = absent_since or now
            if now - absent_since > grace:
                raise SystemExit(
                    f"{tag}job {pid} vanished: not in /history and not queued after {grace:.0f}s — "
                    f"likely a submit failure, not a slow run.")
        else:
            absent_since = None

        if backstop is not None and now - t0 > backstop:
            raise SystemExit(
                f"{tag}backstop {backstop:.0f}s exceeded; job {pid} may STILL be running on the "
                f"server. Recover its output with:  fetch_from_history.py --pid {pid} --out <stem>")

        if now - last_hb >= heartbeat:
            print(f"{tag}waiting {now - t0:.0f}s (state={state}) pid={pid}", flush=True)
            last_hb = now
        time.sleep(poll)


def download_outputs(server: str, hist_entry: dict, out_stem: str | Path, *,
                     kinds: tuple[str, ...] = OUTPUT_KINDS) -> list[Path]:
    """Download every output (videos/gifs/images/audio) of a history entry to `out_stem`.

    Single output -> `out_stem` + its extension. Multiple -> the first uses the stem, the rest get
    an index suffix so nothing is overwritten."""
    server = server.rstrip("/")
    out = Path(out_stem)
    out.parent.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for node in hist_entry.get("outputs", {}).values():
        for kind in kinds:
            for item in node.get(kind, []):
                r = requests.get(f"{server}/view",
                                 params={"filename": item["filename"],
                                         "subfolder": item.get("subfolder", ""),
                                         "type": item.get("type", "output")}, timeout=600)
                r.raise_for_status()
                suffix = Path(item["filename"]).suffix
                p = out.with_suffix(suffix)
                if p in saved:
                    p = out.with_name(f"{out.name}_{len(saved)}{suffix}")
                p.write_bytes(r.content)
                saved.append(p)
    if not saved:
        raise SystemExit(f"no outputs ({', '.join(kinds)}) in history entry to download")
    return saved


def run_job(server: str, graph: dict, out_stem: str | Path, *, kinds: tuple[str, ...] = OUTPUT_KINDS,
            backstop: float | None = None, label: str = "", client_id: str | None = None) -> list[Path]:
    """The canonical single-job round-trip: queue -> wait_for_history -> download. Never times out a
    finished job. Use this (or its parts) instead of a bespoke wait loop."""
    pid = queue(server, graph, client_id)
    hist = wait_for_history(server, pid, backstop=backstop, label=label)
    return download_outputs(server, hist, out_stem, kinds=kinds)


def fetch_from_history(server: str, *, out_stem: str | Path, pid: str | None = None,
                       filename_substr: str | None = None, index: int = -1,
                       kinds: tuple[str, ...] = OUTPUT_KINDS) -> list[Path]:
    """Recover a completed prompt's outputs AFTER THE FACT (the WI 1018 recovery, generalised).

    By `pid` (exact), or by newest match on a `filename_substr` across recent history."""
    server = server.rstrip("/")
    if pid:
        hist = _get_json(server, f"/history/{pid}")
        if pid not in hist:
            raise SystemExit(f"pid {pid} not found in /history")
        return download_outputs(server, hist[pid], out_stem, kinds=kinds)

    hist = _get_json(server, "/history?max_items=50")
    matches = []
    for _pid, entry in hist.items():
        for node in entry.get("outputs", {}).values():
            for kind in kinds:
                for item in node.get(kind, []):
                    if not filename_substr or filename_substr in item.get("filename", ""):
                        matches.append(entry)
    if not matches:
        raise SystemExit(f"no history outputs match filename~={filename_substr!r}")
    return download_outputs(server, matches[index], out_stem, kinds=kinds)
