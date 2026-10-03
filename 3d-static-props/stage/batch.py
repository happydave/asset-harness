#!/usr/bin/env python3
"""Run the stage over a list of props, one at a time, and write one row per prop.

batch.py LIST.json OUTDIR --cpus 12-23 [--only NAME ...]

LIST.json: {"table": ..., "rig": ..., "items": [{"name", "source", "category", "provisional"?, "control"?}]}.
Before any prop it checks its starting conditions and refuses, naming what it saw: its own CPU affinity
is the slice it was given (it is started under taskset), every source exists, and every source's hash
matches its lane record. The ledger's row is checked by whoever starts it, on the host that holds the
ledger. Each prop's verdict, arm, failing rows and time go to OUTDIR/batch.jsonl.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import sha256_file  # noqa: E402


def cpus(spec):
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("out")
    ap.add_argument("--cpus", required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    spec = json.load(open(a.list))
    items = [i for i in spec["items"] if not a.only or i["name"] in a.only]
    problems = []
    have = os.sched_getaffinity(0)
    if have != cpus(a.cpus):
        problems.append(f"affinity is {sorted(have)}, not the slice {a.cpus}")
    for it in items:
        if not os.path.isfile(it["source"]):
            problems.append(f"{it['name']}: no source {it['source']}")
            continue
        if it.get("control"):
            continue
        lane = it["source"] + ".lane.json"
        if not os.path.isfile(lane):
            problems.append(f"{it['name']}: no lane record")
            continue
        want = json.load(open(lane)).get("asset", {}).get("content_hash")
        got = sha256_file(it["source"])
        if want != got:
            problems.append(f"{it['name']}: hash {got} is not the lane record's {want}")
    if problems:
        print("batch refused:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    report = open(os.path.join(a.out, "batch.jsonl"), "a")
    threads = str(len(have))
    for it in items:
        out = os.path.join(a.out, it["name"])
        cmd = [sys.executable, os.path.join(HERE, "stage.py"), it["source"], "--category", it["category"],
               "--table", spec["table"], "--rig", spec["rig"], "--out", out]
        if it.get("control"):
            cmd += ["--control", it["control"]]
        if it.get("provisional"):
            cmd += ["--provisional", it["provisional"]]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "STAGE_THREADS": threads})
        row = {"name": it["name"], "exit": r.returncode, "seconds": round(time.time() - t0, 1),
               "line": (r.stdout.strip().splitlines() or [""])[-1], "stderr": r.stderr.strip()[-500:]}
        side = os.path.join(out, f"{os.path.basename(it['source'])[:-4]}.stage.json")
        if os.path.isfile(side):
            s = json.load(open(side))
            row.update({"result": s["result"], "accepted_arm": s["accepted_arm"],
                        "arms": [{"arm": t["arm"], "failed": t.get("failed"),
                                  "failing_rows": [k for k, v in t.get("gate", {}).items() if not v["pass"]]}
                                 for t in s["arms_tried"]]})
        report.write(json.dumps(row) + "\n")
        report.flush()
        print(f"{it['name']}: exit {r.returncode} in {row['seconds']} s: {row['line']}", flush=True)
    print("batch done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
