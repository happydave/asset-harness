#!/usr/bin/env python3
"""Checks for cull_stills.py. Plain `python3 test_cull_stills.py`; no server, no venv, no GPU, no ffmpeg.

Replays the cull rule on the two archived owner-ranked corpora (the calibration is a permanent test),
then exercises sweep/apply-form/provisional over a fixture manifest with a fake ComfyUI client, a
fake scorer and a fake tiler.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cull_stills as cs
import manifest as M

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {label}{'' if cond else '  — ' + str(detail)}")
    if not cond:
        FAILURES.append(label)


SCORING = Path(__file__).with_name("scoring")

# --- calibration replay -----------------------------------------------------------------------------
A = json.load((SCORING / "machine_scores_v2.json").open())["images"]
B = json.load((SCORING / "baseline_corpus_b.json").open())
OWNER_TOP = {"shot4": "shot4_seed45.png", "shot7": "shot7_seed44.png",          # WI 1037 filled form
             "hero": "hero_s202.png", "lab": "lab_s101.png", "ranch": "ranch_s303.png",  # WI 1111 manifest
             "ai": "ai_s101.png", "readiness": "readiness_s101.png", "games": "games_s101.png"}
real_culled, top_culled, sanity_verdict, n_real = [], [], None, 0
for corpus in (A, B):
    for grp, rec in corpus.items():
        if grp.startswith("_"):
            continue
        v = cs.cull({k: {"clip_letterbox": s["clip_letterbox"], "pickscore_letterbox": s["pickscore_letterbox"]}
                     for k, s in rec["scores"].items()})
        for name, r in v.items():
            if name.startswith("sanity"):
                sanity_verdict = (r["verdict"], r["culled_by"])
                continue
            n_real += 1
            if r["verdict"] == "culled":
                real_culled.append(name)
            if OWNER_TOP.get(grp) == name and r["verdict"] == "culled":
                top_culled.append(name)
check("calibration: 28 real candidates replayed", n_real == 28, n_real)
check("calibration: no real candidate culled", real_culled == [], real_culled)
check("calibration: no owner top pick culled", top_culled == [], top_culled)
check("calibration: the off-brief control is culled", sanity_verdict == ("culled", cs.GATE_BOTH), sanity_verdict)

# --- cull semantics -----------------------------------------------------------------------------------
def grp(**kw):
    return {k: {"clip_letterbox": c, "pickscore_letterbox": p} for k, (c, p) in kw.items()}

v = cs.cull(grp(a=(0.35, 0.20), b=(0.36, 0.21), c=(0.34, 0.19), d=(0.18, 0.15)))
check("cull: both far below -> culled by clip+pickscore", v["d"]["verdict"] == "culled" and v["d"]["culled_by"] == cs.GATE_BOTH, v["d"])
v = cs.cull(grp(a=(0.35, 0.20), b=(0.36, 0.21), c=(0.34, 0.19), d=(0.10, 0.21)))
check("cull: clip catastrophic alone -> culled by clip", v["d"]["culled_by"] == cs.GATE_CLIP, v["d"])
v = cs.cull(grp(a=(0.35, 0.20), b=(0.36, 0.21), c=(0.34, 0.19), d=(0.34, 0.05)))
check("cull: pickscore low alone -> survivor", v["d"]["verdict"] == "survivor", v["d"])
v = cs.cull(grp(a=(0.35, 0.20), b=(0.05, 0.05)))
check("cull: group of 2 -> nothing culled, ratios None", v["b"]["verdict"] == "survivor" and v["b"]["clip_ratio"] is None)
v = cs.cull({"a": {"clip_letterbox": 0.3, "pickscore_letterbox": 0.2}, "b": {}, "c": {"clip_letterbox": 0.3, "pickscore_letterbox": 0.2}})
check("cull: unscored candidate stays survivor, others unaffected", v["b"]["verdict"] == "survivor" and v["a"]["clip_ratio"] is None)
check("shuffle: deterministic per run id + shot", cs.shuffled(["a", "b", "c", "d"], "run1", 3) == cs.shuffled(["a", "b", "c", "d"], "run1", 3))
check("shuffle: differs across shots", cs.shuffled(list("abcdefgh"), "run1", 3) != cs.shuffled(list("abcdefgh"), "run1", 4))
check("form: parse pick + why", cs.parse_form("## shot 03 — x\n- Pick: c\n- Why: warmer light\n## shot 04 — y\n- Pick: \n- Why: \n")
      == {3: {"pick": "C", "why": "warmer light"}, 4: {"pick": "", "why": ""}})

# --- sweep / apply-form / provisional over a fixture --------------------------------------------------------
class FakeClient:
    DEFAULT_SERVER = "x"
    queued = 0
    @staticmethod
    def queue(server, graph):
        FakeClient.queued += 1
        seed = graph["14"]["inputs"]["seed"]; prefix = graph["20"]["inputs"]["filename_prefix"]
        return f"pid:{prefix}:{seed}"
    @staticmethod
    def wait_for_history(server, pid, label=""):
        return {"pid": pid}
    @staticmethod
    def download_outputs(server, hist, stem, kinds=()):
        p = Path(str(stem) + ".png"); p.write_bytes(b"\x89PNG"); return [p]


def fake_scorer(items):
    sc = {}
    for it in items:
        name = Path(it["path"]).name
        # seed 44 of shot 1 is garbage; everything else on-brief
        if name == "shot01_seed44.png":
            sc[it["path"]] = {"clip_letterbox": 0.10, "pickscore_letterbox": 0.13}
        else:
            seed = int(name.split("seed")[1].split(".")[0])
            sc[it["path"]] = {"clip_letterbox": 0.33 + 0.005 * (seed % 5), "pickscore_letterbox": 0.19 + 0.002 * (seed % 5)}
    return {"scores": sc, "controls": {"clip_deterministic": True, "pickscore_deterministic": True},
            "versions": {"clip": "fake-clip", "pickscore": "fake-pick"}}


tiled = []
def fake_tiler(images, dst):
    tiled.append((dst.name, [Path(i).name for i in images])); dst.write_bytes(b"\x89PNG")


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td); cut = tmp / "cut"; (cut / "assets").mkdir(parents=True)
    (cut / "song.flac").write_bytes(b"fLaC")
    shots = []
    for i, kind in enumerate(("kenburns", "still", "video")):
        (cut / "assets" / f"s{i}.png").write_bytes(b"\x89PNG")
        shots.append(M.Shot(index=i, section="verse", lines=[{"index": i, "text": f"line {i}"}],
                            t_start=10.0 * i, t_end=10.0 * (i + 1), kind=kind, prompt=f"prompt {i}",
                            asset=f"assets/s{i}.png"))
    mp = cut / "m.json"
    M.write(M.Manifest(audio="song.flac", duration=30.0, source_timeline="t.json", shots=shots), mp)
    run = cut / "run1"

    summ = cs.sweep(mp, shots=None, n=4, seed_base=41, model="base", run_dir=run,
                    client=FakeClient, scorer=fake_scorer, tiler=fake_tiler)
    m = M.from_json(mp.read_text())
    check("sweep: video shot skipped, still shots swept", FakeClient.queued == 8 and not m.shots[2].candidates and len(m.shots[0].candidates) == 4)
    check("sweep: every candidate recorded with scores + provenance",
          all(c.scores.get("clip_letterbox") is not None and c.provenance["prompt"] == "prompt 0" and c.provenance["lines"] == m.shots[0].lines
              for c in m.shots[0].candidates))
    culled = [c for c in m.shots[1].candidates if c.verdict == "culled"]
    check("sweep: garbage culled with the gate named", len(culled) == 1 and culled[0].asset.endswith("shot01_seed44.png") and culled[0].culled_by == cs.GATE_BOTH, [(c.asset, c.verdict) for c in m.shots[1].candidates])
    check("sweep: summary counts", summ["candidates"] == 8 and summ["culled"] == 1, summ)
    check("sweep: asset untouched until a pick", m.shots[0].asset == "assets/s0.png" and m.shots[0].pick is None)
    check("sweep: recipe carries seed/model/size", m.shots[0].candidates[0].recipe["seed"] == 41 and m.shots[0].candidates[0].recipe["width"] == 1280)
    check("sweep: scorer versions landed", m.scorer_versions == {"still_clip": "fake-clip", "still_pickscore": "fake-pick"}, m.scorer_versions)
    key = json.loads((run / "_tile_key.json").read_text())
    check("sheet: culled candidate absent from key and sheet", "shot01_seed44.png" not in json.dumps(key) and all("seed44" not in n for n in tiled[1][1]))
    check("sheet: shot 1 has 3 survivors lettered A-C", sorted(key["shots"]["shot 01"]) == ["A", "B", "C"])
    check("sheet: tile order is shuffled and recorded", [Path(a).name for a in key["shots"]["shot 00"].values()] == tiled[0][1]
          and list(key["shots"]["shot 00"].values()) == cs.shuffled([c.asset for c in m.shots[0].candidates if c.verdict == "survivor"], "run1", 0))
    form = (run / "pick_form.md").read_text()
    check("form: one section per swept shot, none for the video shot", form.count("## shot") == 2 and "## shot 02" not in form)
    check("manifest validates after sweep", M.validate(m, manifest_dir=cut) is None)
    try:
        cs.sweep(mp, shots=None, n=4, seed_base=41, model="base", run_dir=run, client=FakeClient, scorer=fake_scorer, tiler=fake_tiler)
        check("re-sweep without --replace refused", False)
    except cs.CullError as e:
        check("re-sweep without --replace refused", "--replace" in str(e))

    # apply-form: answer shot 0, leave shot 1 blank
    letter0 = "B"; asset0 = key["shots"]["shot 00"][letter0]
    (run / "pick_form.md").write_text(form.replace("## shot 00", "## shot 00").replace("- Pick: \n- Why: \n", f"- Pick: {letter0}\n- Why: the lantern reads\n", 1))
    r = cs.apply_form(mp, run, date="2026-09-02")
    m = M.from_json(mp.read_text())
    check("apply: shot 0 chosen from the letter, asset updated, owner pick with reason",
          m.shots[0].asset == asset0 and m.shots[0].pick.picked_by == "owner" and m.shots[0].pick.reason == "the lantern reads"
          and sum(c.verdict == "chosen" for c in m.shots[0].candidates) == 1 and sum(c.verdict == "passed-over" for c in m.shots[0].candidates) == 3, r)
    check("apply: blank shot untouched and reported", r["blank"] == [1] and m.shots[1].pick is None and m.shots[1].asset == "assets/s1.png")
    check("manifest validates after apply", M.validate(m, manifest_dir=cut) is None)
    before = mp.read_text()
    (run / "pick_form.md").write_text(form.replace("- Pick: \n- Why: \n", "- Pick: Z\n- Why: nope\n", 1))
    try:
        cs.apply_form(mp, run); check("apply: bad letter refused", False)
    except cs.CullError as e:
        check("apply: bad letter refused, file intact", "not a tile letter" in str(e) and mp.read_text() == before)
    # a second owner pick on shot 0 appends history
    (run / "pick_form.md").write_text(form.replace("- Pick: \n- Why: \n", "- Pick: A\n- Why: changed my mind\n", 1))
    cs.apply_form(mp, run, date="2026-09-03")
    m = M.from_json(mp.read_text())
    check("apply: re-pick appends history with the superseded pick", len(m.shots[0].pick.history) == 1 and m.shots[0].pick.history[0]["asset"] == asset0)

    # provisional: shot 1 (no pick) gets the top PickScore survivor; shot 0 (owner pick) untouched
    r = cs.provisional(mp)
    m = M.from_json(mp.read_text())
    surv = [c for c in m.shots[1].candidates if c.verdict != "culled"]
    top = max(surv, key=lambda c: c.scores["pickscore_letterbox"])
    check("provisional: top PickScore survivor chosen as machine-provisional", r["picked"] == [(1, top.asset)] and m.shots[1].pick.picked_by == "machine-provisional" and m.shots[1].asset == top.asset)
    check("provisional: owner-picked shot untouched", m.shots[0].pick.picked_by == "owner")
    check("provisional: culled candidate never chosen", all(c.verdict == "culled" for c in m.shots[1].candidates if "seed44" in c.asset))
    check("manifest validates after provisional", M.validate(m, manifest_dir=cut) is None)

    # scorer failure: recorded without scores, nothing culled, provisional refuses
    cut2 = tmp / "cut2"; (cut2 / "assets").mkdir(parents=True); (cut2 / "song.flac").write_bytes(b"fLaC"); (cut2 / "assets" / "s0.png").write_bytes(b"\x89PNG")
    mp2 = cut2 / "m.json"
    M.write(M.Manifest(audio="song.flac", duration=10.0, source_timeline="t.json",
                       shots=[M.Shot(index=0, section="v", lines=[{"index": 0, "text": "l"}], t_start=0, t_end=10.0, kind="still", prompt="p", asset="assets/s0.png")]), mp2)
    s2 = cs.sweep(mp2, shots=None, n=3, seed_base=1, model="base", run_dir=cut2 / "r", client=FakeClient,
                  scorer=lambda items: {"error": "venv missing"}, tiler=fake_tiler)
    m2 = M.from_json(mp2.read_text())
    check("scorer failure: candidates recorded as survivors without scores, sheet still built",
          s2["culled"] == 0 and all(c.verdict == "survivor" and "clip_letterbox" not in c.scores for c in m2.shots[0].candidates) and s2["shots"][0]["survivors"] == 3)
    r = cs.provisional(mp2)
    check("scorer failure: provisional skips the shot with a reason", r["picked"] == [] and r["skipped"][0][0] == 0)
    try:
        cs.sweep(mp2, shots=None, n=27, seed_base=1, model="base", run_dir=cut2 / "r2", client=FakeClient, scorer=fake_scorer, tiler=fake_tiler)
        check("n > 26 refused", False)
    except cs.CullError:
        check("n > 26 refused", True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}"); sys.exit(1)
print("all cull_stills checks passed")
