#!/usr/bin/env python3
"""WI 1043: ACE-Step checkpoint race -- XL base vs XL turbo on identical inputs.

Both arms are XL / 9.97 GB / BF16 with identical tensor topology, so the ONLY variable is the
distillation and its sampler regime (base 40 steps @ cfg 5.0, turbo 8 steps @ cfg 1.0). Lyrics, tags,
bpm, key, duration, seeds, encoders, VAE and shift are shared -- see generate_song.CHECKPOINTS.

Three phases, deliberately separate (the WI 1037 lesson: a client held open across a ~500 s job strands
the rest of the batch; submitting is fast and stateless, and ai2's /history is the source of truth):

    ./race.py submit    queue every job, record prompt ids, exit
    ./race.py fetch     wait on /history, download, emit the timing table
    ./race.py blind     build the owner's blind listening folder + form

Timings come from ai2's own execution_start -> execution_success timestamps, not client wall-clock, so
queue waiting is excluded. Jobs are grouped by arm so each 10 GB checkpoint loads once: within an arm
the FIRST job is load-inclusive and the rest are steady-state, and the table reports them separately.
"""
from __future__ import annotations

import json
import shutil
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # prototypes/
import comfy_client  # noqa: E402
import generate_song as gsong  # noqa: E402

SERVER = "http://ai2:8188"
HERE = Path(__file__).resolve().parent
SONGS = HERE / "songs"
BLIND = HERE / "listening"
SUBMITTED = HERE / "submitted.json"
TIMINGS = HERE / "timings.json"

# Grouped by arm so each checkpoint loads once. Two base seeds (not one) so base has a steady-state
# timing too -- comparing base's load-inclusive number against turbo's steady-state would flatter turbo.
ARMS = [("base", [701, 702]), ("turbo", [701, 702, 703, 704])]


def _exec_seconds(hist_entry: dict) -> float | None:
    """Server-side execution time from the history entry's status messages, in seconds."""
    start = end = None
    for msg in hist_entry.get("status", {}).get("messages", []):
        if not (isinstance(msg, list) and len(msg) > 1 and isinstance(msg[1], dict)):
            continue
        event, payload = msg[0], msg[1]
        ts = payload.get("timestamp")
        if ts is None:
            continue
        if event == "execution_start":
            start = ts if start is None else min(start, ts)
        elif event in ("execution_success", "execution_error"):
            end = ts if end is None else max(end, ts)
    return None if start is None or end is None else (end - start) / 1000.0


def submit() -> None:
    jobs = []
    for arm, seeds in ARMS:
        ck = gsong.CHECKPOINTS[arm]
        print(f"-- {arm}: {ck['unet']} steps={ck['steps']} cfg={ck['cfg']}")
        for seed in seeds:
            name = f"{arm}_seed{seed}"
            graph = gsong.build_graph(gsong.SONG, seed, f"asset_harness/wi1043_{name}", checkpoint=arm)
            pid = comfy_client.queue(SERVER, graph)
            jobs.append({"arm": arm, "seed": seed, "name": name, "pid": pid,
                         "dest": str(SONGS / name), "steps": ck["steps"], "cfg": ck["cfg"],
                         "unet": ck["unet"]})
            print(f"   submitted {name} pid={pid[:8]}")
    SUBMITTED.parent.mkdir(parents=True, exist_ok=True)
    SUBMITTED.write_text(json.dumps(jobs, indent=2))
    # the authored lyric sheet is an INPUT; record it beside the artefacts it produced
    gsong.write_lyric_sheet(gsong.SONG, HERE)
    print(f"\n{len(jobs)} jobs -> {SUBMITTED}   (run: ./race.py fetch)")


def fetch() -> None:
    jobs = json.loads(SUBMITTED.read_text())
    for j in jobs:
        hist = comfy_client.wait_for_history(SERVER, j["pid"], label=j["name"])
        paths = comfy_client.download_outputs(SERVER, hist, j["dest"], kinds=("audio",))
        j["path"] = str(paths[0])
        j["exec_s"] = _exec_seconds(hist)
        print(f"{j['name']:16s} {j['exec_s'] or float('nan'):7.1f}s -> {paths[0].name}")
    TIMINGS.write_text(json.dumps(jobs, indent=2))

    print(f"\n{'arm':6s} {'steps':>5s} {'cfg':>4s} {'first(load-incl)':>17s} {'steady mean':>12s} {'n':>3s}")
    for arm, _ in ARMS:
        a = [j for j in jobs if j["arm"] == arm and j.get("exec_s")]
        if not a:
            continue
        steady = [j["exec_s"] for j in a[1:]]
        mean = sum(steady) / len(steady) if steady else float("nan")
        print(f"{arm:6s} {a[0]['steps']:5d} {a[0]['cfg']:4.1f} {a[0]['exec_s']:16.1f}s "
              f"{mean:11.1f}s {len(steady):3d}")
    print(f"\n-> {TIMINGS}")


def blind(src_dir: Path | None = None, out_dir: Path | None = None, round_no: int = 1) -> None:
    """Blind listening set: every song in ONE folder, lettered, arm identity withheld until after."""
    jobs = json.loads((TIMINGS if TIMINGS.exists() else SUBMITTED).read_text())
    if src_dir is not None:  # e.g. the mastered set; match by filename
        for j in jobs:
            cand = src_dir / f"{j['name']}.flac"
            if cand.exists():
                j["path"] = str(cand)
    have = [j for j in jobs if j.get("path") and Path(j["path"]).exists()]
    if not have:
        sys.exit("no downloaded songs yet -- run ./race.py fetch first")
    global BLIND
    BLIND = out_dir or BLIND
    BLIND.mkdir(parents=True, exist_ok=True)
    # Round 1 lettered by (seed, arm). Later rounds MUST use a different permutation, or the owner can
    # carry a letter's reputation over from the previous round instead of re-judging the audio.
    have.sort(key=lambda j: (j["seed"], j["arm"]) if round_no == 1 else (-j["seed"], j["arm"]))
    matched = "\n**All tracks are level-matched** (identical integrated loudness), so perceived volume\n" \
              "cannot bias the comparison -- in an unmatched test the louder track usually wins.\n" \
              "**Letters have been reshuffled since the last round**; they do not correspond.\n" \
        if round_no > 1 else ""
    key, form = {}, [
        f"# WI 1043 blind listening -- ACE-Step base vs turbo (round {round_no})\n",
        "\nEvery track is in THIS folder. They are the **same lyrics, tags, bpm, key and duration**,\n"
        "generated by two different checkpoints. Which checkpoint made which is withheld until you\n"
        "have ranked them (`_arm_key.json` -- do not open it first).\n",
        matched,
        "\nWhat matters most here is **vocal quality**: clarity, timbre, whether the sung lyrics are\n"
        "intelligible and whether the lines land. Ordering alone is worth less than the reasons.\n",
        "\n## Tracks\n",
    ]
    for i, j in enumerate(have):
        letter = string.ascii_uppercase[i]
        dst = BLIND / f"track_{letter}.flac"
        shutil.copyfile(j["path"], dst)
        key[letter] = {"arm": j["arm"], "seed": j["seed"], "steps": j["steps"], "cfg": j["cfg"]}
        form.append(f"  - **{letter}** = `{dst.name}`\n")
    form.append(
        "\n## Ranking\n"
        "- Best -> worst (letters): ______\n"
        "- Why -- what separated best from worst? (vocal clarity? timbre? intelligibility? mix?): ______\n"
        "- Any track where the vocals are clearly a different *class* rather than just a different take? ______\n"
        "- Does anything still sound 'too hot', or does anything have static/popping? Which? ______\n"
        "- Would you change the track's default checkpoint on this evidence? ______\n")
    (BLIND / "listening_form.md").write_text("".join(form))
    (BLIND / "_arm_key.json").write_text(json.dumps(key, indent=2))
    print(f"-> {BLIND}/  ({len(have)} tracks, lettered; arm identity in _arm_key.json)")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "submit":
        submit()
    elif cmd == "fetch":
        fetch()
    elif cmd == "blind":
        # ./race.py blind [src_dir] [out_dir] [round_no]
        src = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        rnd = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        blind(src, out, rnd)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
