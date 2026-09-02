#!/usr/bin/env python3
"""Preflight for the music-video pipeline: check every operational precondition, print the fix.

Read-only. Nothing is restarted, installed or edited -- every fix is printed as the command or the
person to ask. Exit 1 if any check FAILs; WARN and skip never change the exit code, so a driver can
gate on it. Stdlib + requests, no GPU, runs under the system python3.

  server        ComfyUI answers /system_stats
  mmap          comfyui.service runs with --disable-mmap (ssh; a checkpoint load is 6 s with it, ~36 min without)
  queue         nothing running or pending; a running job with an idle GPU is the load-hang fingerprint
  last-job      the previous job was not a Wan clip (else restart before an ACE-Step / Z-Image batch)
  artifacts     the recipe's checkpoints / LoRAs / encoders / VAEs are installed, per requested stage
  ffmpeg        ffmpeg + ffprobe on the workstation PATH (render, clip, align)
  venv-align    music-video/.venv exists (align)
  venv-scoring  prototypes/scoring/.venv exists (song; WARN only -- generate_song.py degrades without it)

Artifact names are imported from generate_clip.py / generate_song.py / generate_still.py so the recipe
has one source of truth. Probes (HTTP, ssh, PATH, filesystem) sit behind one object so the checks run
against a fake in test_preflight.py.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:  # the first precondition of all
    print("FAIL  python        the `requests` package is missing")
    print("      fix: python3 -m pip install --user requests")
    sys.exit(1)

HERE = Path(__file__).resolve().parent
TRACK = HERE.parent
STAGES = ("song", "align", "still", "clip", "render")
DEFAULT_SERVER = "http://ai2:8188"
DEFAULT_HOST = "ai2"
IDLE_GPU_PCT = 10  # healthy idle is ~3 %, compute ~100 %; a running job below this is the hang fingerprint
MMAP_DROPIN = "/etc/systemd/system/comfyui.service.d/disable-mmap-workaround.conf"


class ProbeError(Exception):
    """A probe could not be performed (unreachable server, ssh failure)."""


@dataclass
class Result:
    status: str  # ok | WARN | FAIL | skip
    name: str
    detail: str
    fix: str | None = None


class Probe:
    """The only side-effecting surface. Everything here is read-only."""

    def __init__(self, server: str, host: str, use_ssh: bool = True):
        self.server = server.rstrip("/")
        self.host = host
        self.use_ssh = use_ssh

    def get_json(self, path: str):
        try:
            r = requests.get(f"{self.server}{path}", timeout=15)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            raise ProbeError(str(e)) from e

    def ssh(self, cmd: str) -> str:
        if not self.use_ssh:
            raise ProbeError("ssh disabled (--no-ssh)")
        try:
            out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, cmd],
                                 capture_output=True, text=True, timeout=40)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ProbeError(str(e)) from e
        if out.returncode != 0 and not out.stdout.strip():
            raise ProbeError(out.stderr.strip() or f"ssh exit {out.returncode}")
        return out.stdout

    def which(self, name: str) -> bool:
        return shutil.which(name) is not None

    def exists(self, path: Path) -> bool:
        return Path(path).exists()


# --- pure helpers (tested directly) --------------------------------------------------------------

def parse_gpu_activity(text: str) -> list[int]:
    """Per-GPU busy percentages from `amd-smi metric --usage` or `rocm-smi --showuse` output."""
    pcts = [int(m) for m in re.findall(r"GFX_ACTIVITY:\s*(\d+)\s*%", text)]
    if not pcts:
        pcts = [int(m) for m in re.findall(r"GPU use \(%\):\s*(\d+)", text)]
    return pcts


def last_job_classes(history: dict) -> set[str] | None:
    """class_type set of the newest history entry's graph; empty set if no history; None if unreadable."""
    if not history:
        return set()
    try:
        entry = next(iter(history.values()))
        graph = entry["prompt"][2]
        return {node.get("class_type") for node in graph.values()}
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def artifact_requirements(stages: set[str]) -> list[tuple[str, str, str, str]]:
    """(loader class, option field, artifact name, stage) for every model file a requested stage loads."""
    reqs: list[tuple[str, str, str, str]] = []
    if "clip" in stages:
        import generate_clip as gc
        reqs += [("UNETLoader", "unet_name", gc.HIGH_UNET, "clip"),
                 ("UNETLoader", "unet_name", gc.LOW_UNET, "clip"),
                 ("LoraLoaderModelOnly", "lora_name", gc.HIGH_LORA, "clip"),
                 ("LoraLoaderModelOnly", "lora_name", gc.LOW_LORA, "clip"),
                 ("CLIPLoader", "clip_name", gc.CLIP, "clip"),
                 ("VAELoader", "vae_name", gc.VAE, "clip")]
    if "song" in stages:
        import generate_song as gs
        reqs += [("UNETLoader", "unet_name", ck["unet"], "song") for ck in gs.CHECKPOINTS.values()]
        reqs += [("DualCLIPLoader", "clip_name1", gs.CLIP1, "song"),
                 ("DualCLIPLoader", "clip_name1", gs.CLIP2, "song"),
                 ("VAELoader", "vae_name", gs.VAE, "song")]
    if "still" in stages:
        import generate_still as gi
        reqs += [("UNETLoader", "unet_name", m["unet"], "still") for m in gi.MODELS.values()]
        reqs += [("CLIPLoader", "clip_name", gi.CLIP, "still"),
                 ("VAELoader", "vae_name", gi.VAE, "still")]
    return reqs


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.status == "FAIL" for r in results) else 0


# --- the checks ----------------------------------------------------------------------------------

def run_checks(probe: Probe, *, stages: set[str], track: Path = TRACK) -> list[Result]:
    results: list[Result] = []
    host = probe.host
    restart = f"ssh {host} systemctl restart comfyui.service"

    # 1. server
    try:
        stats = probe.get_json("/system_stats")
        version = stats.get("system", {}).get("comfyui_version", "?")
        results.append(Result("ok", "server", f"ComfyUI {version} at {probe.server}"))
        server_up = True
    except ProbeError as e:
        results.append(Result("FAIL", "server", f"{probe.server} did not answer /system_stats ({e})",
                              f"check the host and port (--server), then: ssh {host} systemctl status comfyui.service"))
        server_up = False

    # 2. mmap flag
    try:
        exec_start = probe.ssh("systemctl show comfyui.service -p ExecStart")
        if "argv[]=" not in exec_start:
            results.append(Result("FAIL", "mmap", f"comfyui.service has no ExecStart on {host} (unit missing or renamed)",
                                  f"ssh {host} systemctl list-units 'comfyui*' -- the service name this check expects is comfyui.service"))
        elif "--disable-mmap" in exec_start:
            results.append(Result("ok", "mmap", "comfyui.service runs with --disable-mmap"))
        else:
            results.append(Result("FAIL", "mmap", "--disable-mmap is missing from comfyui.service ExecStart "
                                  "(a checkpoint load costs ~36 min without it, 6 s with it)",
                                  f"the flag comes from {MMAP_DROPIN} (renamed .disabled = off). Shared service: "
                                  "report it to the owner; do not edit the unit yourself"))
    except ProbeError as e:
        results.append(Result("skip", "mmap", f"ssh to {host} unavailable ({e}); check by hand: "
                              f"ssh {host} 'systemctl show comfyui.service -p ExecStart | grep -o -- --disable-mmap'"))

    # 3. queue + load-hang fingerprint
    running = 0
    if server_up:
        try:
            q = probe.get_json("/queue")
            running = len(q.get("queue_running", []))
            pending = len(q.get("queue_pending", []))
            if running or pending:
                results.append(Result("WARN", "queue", f"{running} running, {pending} pending; a batch queues behind them",
                                      "wait, or check whose job it is before adding load"))
            else:
                results.append(Result("ok", "queue", "idle"))
        except ProbeError as e:
            results.append(Result("skip", "queue", f"/queue unreadable ({e})"))
    else:
        results.append(Result("skip", "queue", "server unreachable"))

    if running:
        try:
            gpu_text = probe.ssh("amd-smi metric --usage 2>/dev/null || rocm-smi --showuse")
            pcts = parse_gpu_activity(gpu_text)
            if not pcts:
                results.append(Result("skip", "gpu", "neither amd-smi nor rocm-smi reported GPU activity"))
            elif max(pcts) < IDLE_GPU_PCT:
                results.append(Result("WARN", "gpu", f"a job is running but GPU activity is {pcts} % -- a running job "
                                      "with the GPU idle is how the silent load hang looks",
                                      f"if this persists more than two minutes: {restart}"))
            else:
                results.append(Result("ok", "gpu", f"activity {pcts} % with a job running"))
        except ProbeError as e:
            results.append(Result("skip", "gpu", f"GPU probe over ssh failed ({e}); fingerprint not sampled"))

    # 4. last job Wan
    if server_up and stages & {"song", "still"}:
        try:
            classes = last_job_classes(probe.get_json("/history?max_items=1"))
            if classes is None:
                results.append(Result("skip", "last-job", "could not read the last job's graph"))
            elif "WanImageToVideo" in classes:
                results.append(Result("WARN", "last-job", "the last job was a Wan clip; the model manager may now be "
                                      "evicting every job (each one re-reads its models from disk)",
                                      f"before an ACE-Step / Z-Image batch: {restart}"))
            else:
                results.append(Result("ok", "last-job", "last job was not a Wan clip" if classes else "no history"))
        except ProbeError as e:
            results.append(Result("skip", "last-job", f"/history unreadable ({e})"))

    # 5. artifacts
    if server_up:
        loaders: dict[str, dict | None] = {}
        for loader, field, name, stage in artifact_requirements(stages):
            if loader not in loaders:
                try:
                    info = probe.get_json(f"/object_info/{loader}")
                    loaders[loader] = info.get(loader, {}).get("input", {}).get("required", {})
                except ProbeError:
                    loaders[loader] = None
            req = loaders[loader]
            label = f"artifact:{stage}"
            if req is None:
                results.append(Result("FAIL", label, f"loader {loader} is not registered on this ComfyUI",
                                      f"{name} needs {loader}; check the ComfyUI install on {host}"))
                continue
            options = req.get(field, [[]])[0] if isinstance(req.get(field), list) else []
            if name in options:
                results.append(Result("ok", label, f"{name} ({loader})"))
            else:
                results.append(Result("FAIL", label, f"{name} not in {loader}.{field}",
                                      f"install {name} under ComfyUI's models folder on {host} -- a model install on the "
                                      "shared box is an owner work item, not an operator step"))
    elif artifact_requirements(stages):
        results.append(Result("skip", "artifacts", "server unreachable"))

    # 6. ffmpeg
    if stages & {"render", "clip", "align"}:
        missing = [t for t in ("ffmpeg", "ffprobe") if not probe.which(t)]
        if missing:
            results.append(Result("FAIL", "ffmpeg", f"{', '.join(missing)} not on PATH",
                                  f"install ffmpeg on this workstation (assembly runs here, not on {host})"))
        else:
            results.append(Result("ok", "ffmpeg", "ffmpeg + ffprobe on PATH"))

    # 7. alignment venv
    if "align" in stages:
        py = track / ".venv" / "bin" / "python"
        if probe.exists(py):
            results.append(Result("ok", "venv-align", str(py)))
        else:
            results.append(Result("FAIL", "venv-align", f"{py} missing",
                                  f"cd {track} && python3 -m venv .venv && .venv/bin/pip install demucs whisperx  (~7.6 GB)"))

    # 8. scoring venv
    if "song" in stages:
        py = track / "prototypes" / "scoring" / ".venv" / "bin" / "python"
        if probe.exists(py):
            results.append(Result("ok", "venv-scoring", str(py)))
        else:
            results.append(Result("WARN", "venv-scoring", f"{py} missing; generate_song.py will skip the -1 dBTP "
                                  "ceiling and say so",
                                  f"cd {track / 'prototypes' / 'scoring'} && python3 -m venv .venv && "
                                  ".venv/bin/pip install <the packages named in the scoring/*.py headers>"))
    return results


def report(results: list[Result]) -> None:
    for r in results:
        print(f"{r.status:<5} {r.name:<14} {r.detail}")
        if r.fix and r.status in ("FAIL", "WARN"):
            print(f"      fix: {r.fix}")
    n = {s: sum(1 for r in results if r.status == s) for s in ("ok", "WARN", "FAIL", "skip")}
    print(f"-- {n['ok']} ok, {n['WARN']} warn, {n['FAIL']} fail, {n['skip']} skipped -> exit {exit_code(results)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--host", default=DEFAULT_HOST, help="ssh host running ComfyUI")
    ap.add_argument("--no-ssh", action="store_true", help="skip ssh-backed checks (mmap flag, GPU fingerprint)")
    ap.add_argument("--stage", action="append", choices=STAGES,
                    help="check only these stages (repeatable); default: all")
    args = ap.parse_args(argv)
    stages = set(args.stage) if args.stage else set(STAGES)
    results = run_checks(Probe(args.server, args.host, use_ssh=not args.no_ssh), stages=stages)
    report(results)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
