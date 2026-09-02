#!/usr/bin/env python3
"""Checks for preflight.py. Plain `python3 test_preflight.py`, no pytest, no server, no ssh, no GPU.

Same convention as test_chain.py: exits non-zero on failure. Every probe is faked, so each check's pass
and fail path is exercised deterministically; one subprocess check confirms the real CLI fails fast on
an unreachable server.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_clip as gc
import generate_song as gs
import generate_still as gi
import preflight as pf

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + detail}")
    if not cond:
        FAILURES.append(label)


AMD_SMI = "GPU: 0\n    USAGE:\n        GFX_ACTIVITY: {a} %\n        UMC_ACTIVITY: 0 %\nGPU: 1\n    USAGE:\n        GFX_ACTIVITY: {b} %\n"
ROCM_SMI = "==== ROCm SMI ====\nGPU[0]\t\t: GPU use (%): {a}\nGPU[1]\t\t: GPU use (%): {b}\n==== End ====\n"
EXEC_ON = "ExecStart={ path=/opt/comfyui-env/bin/python ; argv[]=/opt/comfyui-env/bin/python main.py --listen 0.0.0.0 --port 8188 --disable-mmap ; ignore_errors=no }\n"
EXEC_OFF = EXEC_ON.replace(" --disable-mmap", "")
WAN_GRAPH = {"30": {"class_type": "WanImageToVideo", "inputs": {}}, "50": {"class_type": "VAEDecode", "inputs": {}}}
STILL_GRAPH = {"1": {"class_type": "CLIPLoader", "inputs": {}}, "9": {"class_type": "KSampler", "inputs": {}}}


def history(graph):
    return {"pid-1": {"prompt": [1, "pid-1", graph, {}, ["52"]], "outputs": {}, "status": {}, "meta": {}}}


def object_info(loader, field, names):
    return {loader: {"input": {"required": {field: [list(names), {}]}}}}


ALL_NAMES = {
    ("UNETLoader", "unet_name"): [gc.HIGH_UNET, gc.LOW_UNET, gi.MODELS["base"]["unet"], gi.MODELS["zanime"]["unet"]]
                                 + [ck["unet"] for ck in gs.CHECKPOINTS.values()],
    ("LoraLoaderModelOnly", "lora_name"): [gc.HIGH_LORA, gc.LOW_LORA],
    ("CLIPLoader", "clip_name"): [gc.CLIP, gi.CLIP],
    ("DualCLIPLoader", "clip_name1"): [gs.CLIP1, gs.CLIP2],
    ("VAELoader", "vae_name"): [gc.VAE, gs.VAE, gi.VAE],
}


class FakeProbe:
    """A healthy ai2 by default; tests break one thing at a time."""

    def __init__(self, **over):
        self.server = "http://fake:8188"
        self.host = "fake"
        self.json = {"/system_stats": {"system": {"comfyui_version": "0.22.0"}},
                     "/queue": {"queue_running": [], "queue_pending": []},
                     "/history?max_items=1": history(STILL_GRAPH)}
        for (loader, field), names in ALL_NAMES.items():
            self.json[f"/object_info/{loader}"] = object_info(loader, field, names)
        self.ssh_out = {"systemctl show": EXEC_ON, "amd-smi": AMD_SMI.format(a=97, b=0)}
        self.ssh_fail = False
        self.server_down = False
        self.tools = {"ffmpeg", "ffprobe"}
        self.paths = {pf.TRACK / ".venv" / "bin" / "python",
                      pf.TRACK / "prototypes" / "scoring" / ".venv" / "bin" / "python"}
        for k, v in over.items():
            setattr(self, k, v)

    def get_json(self, path):
        if self.server_down:
            raise pf.ProbeError("connection refused")
        if path not in self.json:
            raise pf.ProbeError(f"404 {path}")
        return self.json[path]

    def ssh(self, cmd):
        if self.ssh_fail:
            raise pf.ProbeError("ssh: connect to host fake port 22: No route to host")
        for key, out in self.ssh_out.items():
            if key in cmd:
                return out
        raise pf.ProbeError(f"no fake for {cmd!r}")

    def which(self, name):
        return name in self.tools

    def exists(self, path):
        return Path(path) in self.paths


ALL = set(pf.STAGES)


def by_name(results, name):
    return [r for r in results if r.name == name]


def status(results, name):
    rs = by_name(results, name)
    return rs[0].status if rs else None


# --- pure helpers --------------------------------------------------------------------------------
check("parse amd-smi", pf.parse_gpu_activity(AMD_SMI.format(a=3, b=0)) == [3, 0])
check("parse rocm-smi fallback", pf.parse_gpu_activity(ROCM_SMI.format(a=98, b=0)) == [98, 0])
check("parse nothing", pf.parse_gpu_activity("no tools here") == [])
check("last job classes: wan", "WanImageToVideo" in pf.last_job_classes(history(WAN_GRAPH)))
check("last job classes: empty history", pf.last_job_classes({}) == set())
check("last job classes: unreadable shape", pf.last_job_classes({"p": {"prompt": "bogus"}}) is None)
reqs = pf.artifact_requirements(ALL)
check("artifact requirements: one source of truth",
      {r[2] for r in reqs} == {n for names in ALL_NAMES.values() for n in names},
      f"{sorted({r[2] for r in reqs} ^ {n for names in ALL_NAMES.values() for n in names})}")
check("artifact requirements: clip only excludes song/still", {r[3] for r in pf.artifact_requirements({"clip"})} == {"clip"})
check("artifact requirements: render only needs none", pf.artifact_requirements({"render"}) == [])

# --- happy path ----------------------------------------------------------------------------------
res = pf.run_checks(FakeProbe(), stages=ALL)
check("happy: exit 0", pf.exit_code(res) == 0, str([(r.name, r.status, r.detail) for r in res if r.status != "ok"]))
check("happy: no WARN/FAIL/skip", all(r.status == "ok" for r in res), str([r for r in res if r.status != "ok"]))
check("happy: every check present", {r.name for r in res} >= {"server", "mmap", "queue", "last-job", "ffmpeg",
                                                                 "venv-align", "venv-scoring", "artifact:clip",
                                                                 "artifact:song", "artifact:still"})
check("happy: gpu not sampled when idle", status(res, "gpu") is None)

# --- each failure path names its fix -------------------------------------------------------------
res = pf.run_checks(FakeProbe(server_down=True), stages=ALL)
check("server down: FAIL + fix", status(res, "server") == "FAIL" and "systemctl status" in by_name(res, "server")[0].fix)
check("server down: dependent checks skip, not fail",
      status(res, "queue") == "skip" and status(res, "artifacts") == "skip" and status(res, "last-job") is None)
check("server down: mmap still checked over ssh", status(res, "mmap") == "ok")
check("server down: exit 1", pf.exit_code(res) == 1)

res = pf.run_checks(FakeProbe(ssh_out={"systemctl show": EXEC_OFF}), stages=ALL)
r = by_name(res, "mmap")[0]
check("mmap off: FAIL", r.status == "FAIL")
check("mmap off: fix names the drop-in and the owner", pf.MMAP_DROPIN in r.fix and "owner" in r.fix)
check("mmap off: exit 1", pf.exit_code(res) == 1)

res = pf.run_checks(FakeProbe(ssh_out={"systemctl show": "ExecStart=\n"}), stages=ALL)
check("unit missing: FAIL names the service, not the flag", status(res, "mmap") == "FAIL"
      and "no ExecStart" in by_name(res, "mmap")[0].detail and "list-units" in by_name(res, "mmap")[0].fix)

p = FakeProbe(ssh_fail=True)
res = pf.run_checks(p, stages=ALL)
check("ssh unavailable: mmap skip with by-hand command", status(res, "mmap") == "skip" and "grep -o" in by_name(res, "mmap")[0].detail)
check("ssh unavailable: exit still 0", pf.exit_code(res) == 0)

p = FakeProbe()
p.json["/queue"] = {"queue_running": [[1, "pid-x"]], "queue_pending": [[2, "pid-y"]]}
p.ssh_out["amd-smi"] = AMD_SMI.format(a=3, b=0)
res = pf.run_checks(p, stages=ALL)
check("busy queue: WARN with counts", status(res, "queue") == "WARN" and "1 running, 1 pending" in by_name(res, "queue")[0].detail)
check("hang fingerprint: WARN not FAIL", status(res, "gpu") == "WARN")
check("hang fingerprint: fix says persist + restart", "two minutes" in by_name(res, "gpu")[0].fix
      and "systemctl restart comfyui.service" in by_name(res, "gpu")[0].fix)
check("hang fingerprint: exit 0 (a warning)", pf.exit_code(res) == 0)
p.ssh_out["amd-smi"] = AMD_SMI.format(a=98, b=0)
res = pf.run_checks(p, stages=ALL)
check("busy GPU with running job: ok", status(res, "gpu") == "ok")
p.ssh_out["amd-smi"] = ROCM_SMI.format(a=3, b=0)
res = pf.run_checks(p, stages=ALL)
check("rocm-smi fallback output: fingerprint still detected", status(res, "gpu") == "WARN")
p.ssh_out["amd-smi"] = "bash: amd-smi: command not found\nbash: rocm-smi: command not found\n"
res = pf.run_checks(p, stages=ALL)
check("no GPU tool: skip", status(res, "gpu") == "skip")
p.ssh_fail = True
res = pf.run_checks(p, stages=ALL)
check("running job, no ssh: gpu skip", status(res, "gpu") == "skip")

p = FakeProbe()
p.json["/history?max_items=1"] = history(WAN_GRAPH)
res = pf.run_checks(p, stages=ALL)
check("last job Wan + song requested: WARN with restart", status(res, "last-job") == "WARN"
      and "systemctl restart comfyui.service" in by_name(res, "last-job")[0].fix)
res = pf.run_checks(p, stages={"clip"})
check("last job Wan + clip only: no warning", status(res, "last-job") is None)
p.json["/history?max_items=1"] = {}
res = pf.run_checks(p, stages=ALL)
check("empty history: ok", status(res, "last-job") == "ok")
p.json["/history?max_items=1"] = {"p": {"prompt": "bogus"}}
res = pf.run_checks(p, stages=ALL)
check("unreadable history: skip, no crash", status(res, "last-job") == "skip")

for loader, field in ALL_NAMES:
    p = FakeProbe()
    names = list(ALL_NAMES[(loader, field)])
    dropped = names.pop()
    p.json[f"/object_info/{loader}"] = object_info(loader, field, names)
    res = pf.run_checks(p, stages=ALL)
    bad = [r for r in res if r.name.startswith("artifact:") and r.status == "FAIL"]
    check(f"missing {loader} artifact: exactly one FAIL naming it",
          len(bad) == 1 and dropped in bad[0].detail and "install" in bad[0].fix and "owner" in bad[0].fix,
          str([(r.detail, r.fix) for r in bad]))
    check(f"missing {loader} artifact: exit 1", pf.exit_code(res) == 1)
p = FakeProbe()
del p.json["/object_info/LoraLoaderModelOnly"]
res = pf.run_checks(p, stages={"clip"})
bad = [r for r in res if r.name == "artifact:clip" and r.status == "FAIL"]
check("loader not registered: FAIL per artifact of that loader", len(bad) == 2 and all("not registered" in r.detail for r in bad))

res = pf.run_checks(FakeProbe(tools={"ffmpeg"}), stages={"render"})
check("ffprobe missing: FAIL names it + workstation fix", status(res, "ffmpeg") == "FAIL"
      and "ffprobe" in by_name(res, "ffmpeg")[0].detail and "workstation" in by_name(res, "ffmpeg")[0].fix)
res = pf.run_checks(FakeProbe(tools=set()), stages={"song"})
check("song stage alone does not need ffmpeg", status(res, "ffmpeg") is None)

res = pf.run_checks(FakeProbe(paths=set()), stages=ALL)
check("align venv missing: FAIL with the venv command", status(res, "venv-align") == "FAIL"
      and "pip install demucs whisperx" in by_name(res, "venv-align")[0].fix)
check("scoring venv missing: WARN (generate_song degrades)", status(res, "venv-scoring") == "WARN"
      and "ceiling" in by_name(res, "venv-scoring")[0].detail)
res = pf.run_checks(FakeProbe(paths=set()), stages={"clip"})
check("clip only: no venv checks", status(res, "venv-align") is None and status(res, "venv-scoring") is None)

# --- stage selection --------------------------------------------------------------------------------
res = pf.run_checks(FakeProbe(), stages={"clip"})
check("clip only: no song/still artifacts", not any(r.name in ("artifact:song", "artifact:still") for r in res))
check("clip only: clip artifacts checked", len(by_name(res, "artifact:clip")) == 6)

# --- the real CLI against an unreachable server ---------------------------------------------------
proc = subprocess.run([sys.executable, str(Path(__file__).with_name("preflight.py")),
                       "--server", "http://127.0.0.1:9", "--no-ssh", "--stage", "render"],
                      capture_output=True, text=True, timeout=60)
check("cli: unreachable server exits 1", proc.returncode == 1, proc.stdout + proc.stderr)
check("cli: prints FAIL server with a fix line", "FAIL  server" in proc.stdout and "fix:" in proc.stdout, proc.stdout)
check("cli: --no-ssh reports mmap as skip", "skip  mmap" in proc.stdout, proc.stdout)
check("cli: summary line", "-> exit 1" in proc.stdout, proc.stdout)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("all preflight checks passed")
