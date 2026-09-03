#!/usr/bin/env python3
"""Checks for clip_candidates.py. Plain `python3 test_clip_candidates.py`; no server, no ffmpeg, no GPU.
The ComfyUI client, chain builder, prober, motion probe, sheet builder and opaque check are all faked.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clip_candidates as clc
import cull_stills as cs
import manifest as M

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + str(detail)}")
    if not cond:
        FAILURES.append(label)


# --- pure gates ---------------------------------------------------------------------------------------
P = {"width": 1280, "height": 720, "frames": 33, "fps": "16/1"}
check("fps parse", clc.fps_value("16/1") == 16.0 and clc.fps_value(16) == 16.0)
check("gate: good clip survives", clc.gate(P, frames=33, fps=16, width=1280, height=720)[0] == "survivor")
check("gate: wrong frames -> integrity:frames", clc.gate({**P, "frames": 32}, frames=33, fps=16, width=1280, height=720)[1] == clc.GATE_FRAMES)
check("gate: wrong fps -> integrity:fps", clc.gate({**P, "fps": "24/1"}, frames=33, fps=16, width=1280, height=720)[1] == clc.GATE_FPS)
check("gate: wrong size -> integrity:size", clc.gate({**P, "width": 832, "height": 480}, frames=33, fps=16, width=1280, height=720)[1] == clc.GATE_SIZE)
check("gate: unreadable -> integrity:unreadable", clc.gate(None, frames=33, fps=16, width=1280, height=720)[1] == clc.GATE_UNREADABLE)
seams_bad_ssim = [{"ssim_pass": False, "acuity_pass": True}]
seams_bad_acu = [{"ssim_pass": True, "acuity_pass": False}]
check("gate: chained seam ssim fail -> seam:ssim", clc.gate({**P, "frames": 66}, frames=66, fps=16, width=1280, height=720, seams=seams_bad_ssim)[1] == clc.GATE_SSIM)
check("gate: chained acuity fail -> seam:acuity", clc.gate({**P, "frames": 66}, frames=66, fps=16, width=1280, height=720, seams=seams_bad_acu)[1] == clc.GATE_ACUITY)
check("gate: integrity precedes seams", clc.gate({**P, "frames": 60}, frames=66, fps=16, width=1280, height=720, seams=seams_bad_ssim)[1] == clc.GATE_FRAMES)
try:
    clc.check_adjacent(2, 3); check("adjacency refused", False)
except clc.ClipError as e:
    check("adjacency refused with the WI 1160 rule", "WI 1160" in str(e))
clc.check_adjacent(2, 4); check("non-adjacent source allowed", True)

# --- sweep over a fixture ------------------------------------------------------------------------------
class FakeClient:
    DEFAULT_SERVER = "x"; queued = []
    @staticmethod
    def queue(server, graph):
        seed = graph["40"]["inputs"]["noise_seed"]; FakeClient.queued.append(seed); return f"pid{seed}"
    @staticmethod
    def wait_for_history(server, pid, label=""): return {"pid": pid}
    @staticmethod
    def download_outputs(server, hist, stem, kinds=()):
        p = Path(str(stem) + ".mp4"); p.write_bytes(b"mp4"); return [p]


def fake_prober(path):
    name = Path(path).name
    if "seed902" in name:
        return {"width": 1280, "height": 720, "frames": 32, "fps": "16/1"}   # one frame short
    if "chain" in name:
        return {"width": 1280, "height": 720, "frames": 66, "fps": "16/1"}
    return {"width": 1280, "height": 720, "frames": 33, "fps": "16/1"}


def fake_motion(path):
    return {"motion_scene_n": 32, "motion_scene_mean": 0.0123, "motion_scene_max": 0.05}


sheets = []
def fake_sheet(clips, letters, dst):
    sheets.append(([Path(c).name for c in clips], letters)); dst.write_bytes(b"png")


def fixture(tmp):
    cut = tmp / "cut"; (cut / "assets").mkdir(parents=True); (cut / "song.flac").write_bytes(b"fLaC")
    shots = []
    for i in range(5):
        (cut / "assets" / f"s{i}.png").write_bytes(b"\x89PNG")
        shots.append(M.Shot(index=i, section="v", lines=[{"index": i, "text": f"l{i}"}], t_start=10.0 * i,
                            t_end=10.0 * (i + 1), kind="video" if i == 2 else "kenburns", prompt=f"p{i}",
                            asset=f"assets/s{i}.png"))
    mp = cut / "m.json"
    M.write(M.Manifest(audio="song.flac", duration=50.0, source_timeline="t.json", shots=shots), mp)
    return cut, mp


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td); cut, mp = fixture(tmp); run = cut / "clips"
    common = dict(client=FakeClient, prober=fake_prober, motion=fake_motion, sheet=fake_sheet, opaque_check=lambda p: None)

    try:
        clc.sweep(mp, shot=2, source_shot=3, prompt="mist", n=2, run_dir=run, **common); check("sweep: adjacent source refused before queueing", False)
    except clc.ClipError:
        check("sweep: adjacent source refused before queueing", FakeClient.queued == [])
    try:
        clc.sweep(mp, shot=1, source_shot=4, prompt="mist", n=2, run_dir=run, **common); check("sweep: non-video shot refused without --make-video", False)
    except clc.ClipError as e:
        check("sweep: non-video shot refused without --make-video", "--make-video" in str(e))
    try:
        clc.sweep(mp, shot=2, source_shot=4, prompt="mist", n=5, run_dir=run, **common); check("sweep: n > 4 refused", False)
    except clc.ClipError:
        check("sweep: n > 4 refused", True)

    summ = clc.sweep(mp, shot=2, source_shot=4, prompt="mist drifting", n=3, seed_base=901, run_dir=run, **common)
    m = M.from_json(mp.read_text())
    s = m.shots[2]
    check("sweep: three queued, three recorded", FakeClient.queued == [901, 902, 903] and len(s.candidates) == 3)
    culled = [c for c in s.candidates if c.verdict == "culled"]
    check("sweep: short clip culled by integrity:frames", len(culled) == 1 and culled[0].culled_by == clc.GATE_FRAMES and "seed902" in culled[0].asset, [(c.asset, c.verdict, c.culled_by) for c in s.candidates])
    check("sweep: motion report on every candidate incl. the culled one", all(c.scores.get("motion_scene_mean") == 0.0123 for c in s.candidates))
    check("sweep: recipe + provenance recorded", s.candidates[0].recipe["seed"] == 901 and s.candidates[0].recipe["frames"] == 33
          and s.candidates[0].provenance == {"source_shot": 4, "source_still": "assets/s4.png", "prompt": "mist drifting"})
    check("sweep: asset untouched until a pick", s.asset == "assets/s2.png" and s.pick is None)
    key = json.loads((run / "_tile_key.json").read_text())["shots"]["shot 02"]
    check("sheet: only survivors, shuffled + lettered", sorted(key) == ["A", "B"] and "seed902" not in json.dumps(key)
          and sheets[-1][0] == [Path(a).name for a in key.values()])
    check("sheet: order recorded == cs.shuffled", list(key.values()) == cs.shuffled([c.asset for c in s.candidates if c.verdict == "survivor"], "clips", 2))
    check("form: one section for shot 02", "## shot 02" in (run / "pick_form.md").read_text())
    check("manifest validates after sweep", M.validate(m, manifest_dir=cut) is None)
    check("summary", summ["candidates"] == 3 and summ["survivors"] == 2 and summ["sheet"] == "shot02_sheet.png", summ)
    try:
        clc.sweep(mp, shot=2, source_shot=4, prompt="mist", n=2, run_dir=run, **common); check("re-sweep refused without --replace", False)
    except clc.ClipError as e:
        check("re-sweep refused without --replace", "--replace" in str(e))

    # provisional: first survivor (seed 901), labelled
    r = clc.provisional(mp, 2)
    m = M.from_json(mp.read_text()); s = m.shots[2]
    check("provisional: first survivor chosen, asset set, machine-provisional", r["picked"].endswith("seed901.mp4") and s.asset.endswith("seed901.mp4")
          and s.pick.picked_by == "machine-provisional" and "no video aesthetic" in s.pick.reason)
    check("provisional: culled never chosen; other survivor passed-over", [c.verdict for c in s.candidates] == ["chosen", "culled", "passed-over"])
    check("manifest validates after provisional (adjacency lint satisfied)", M.validate(m, manifest_dir=cut) is None)
    check("provisional: second call skipped", "skipped" in clc.provisional(mp, 2))

    # apply-form via the shared still-stage machinery on a fresh sweep
    clc.sweep(mp, shot=2, source_shot=4, prompt="mist drifting", n=2, seed_base=911, run_dir=run, replace=True, **common)
    key = json.loads((run / "_tile_key.json").read_text())["shots"]["shot 02"]
    form = (run / "pick_form.md").read_text().replace("- Pick: \n- Why: \n", "- Pick: B\n- Why: the lamp swings\n", 1)
    (run / "pick_form.md").write_text(form)
    r = cs.apply_form(mp, run, date="2026-09-02")
    m = M.from_json(mp.read_text()); s = m.shots[2]
    check("apply-form: owner pick on the clip shot with reason", s.asset == key["B"] and s.pick.picked_by == "owner" and s.pick.reason == "the lamp swings", r)

    # chained candidates: fake builder returns a seam report; one fails ssim
    def fake_builder(server, image, prompts, links, out_stem, **kw):
        out = out_stem.with_suffix(".mp4"); out.write_bytes(b"mp4")
        bad = kw["seed"] == 922
        return {"output": str(out), "links": links, "link_frames": [33] * links, "total_frames": 33 * links,
                "seams": [{"seam": 1, "gap": 0.09 if bad else 0.003, "ssim_pass": not bad, "acuity_pass": True, "pass": not bad}]}
    def chain_prober(path):
        return {"width": 1280, "height": 720, "frames": 66, "fps": "16/1"}
    clc.sweep(mp, shot=2, source_shot=0, prompt="glide", n=2, seed_base=921, links=2, run_dir=cut / "chains", replace=True,
              chain_builder=fake_builder, prober=chain_prober, motion=fake_motion, sheet=fake_sheet, opaque_check=lambda p: None)
    m = M.from_json(mp.read_text()); s = m.shots[2]
    check("chain: seam ssim failure culled by seam:ssim, seams recorded", [c.culled_by for c in s.candidates] == ["", clc.GATE_SSIM]
          and s.candidates[1].scores["seams"][0]["gap"] == 0.09)
    check("chain: expected frames = frames x links", s.candidates[0].scores["expected_frames"] == 66 and s.candidates[0].recipe["links"] == 2)
    check("chain: report written", (cut / "chains" / "shot02_seed921.chain.json").exists())

    # provisional with no survivors refuses
    def all_bad_prober(path): return None
    clc.sweep(mp, shot=2, source_shot=0, prompt="x", n=1, run_dir=cut / "bad", replace=True, client=FakeClient, prober=all_bad_prober,
              motion=fake_motion, sheet=fake_sheet, opaque_check=lambda p: None)
    try:
        clc.provisional(mp, 2); check("provisional: no survivors refused", False)
    except clc.ClipError as e:
        check("provisional: no survivors refused with re-sweep", "re-sweep" in str(e))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}"); sys.exit(1)
print("all clip_candidates checks passed")
