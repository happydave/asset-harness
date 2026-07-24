#!/usr/bin/env python3
"""WI 1037: fetch every submitted candidate from ai2 /history to its dest. Re-runnable.

Reads submitted.json (from submit_all.py). For each prompt still missing on disk, tries to recover its
output from /history by prompt_id. Prints how many are done / still pending, so it can be re-run until
the queue drains. Never fails the whole batch on one missing item.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # prototypes/
import comfy_client

SERVER = "http://ai2:8188"
HERE = Path(__file__).resolve().parent


def main():
    items = json.loads((HERE / "submitted.json").read_text())
    done = pending = 0
    for it in items:
        dest = Path(it["dest"])
        if dest.exists():
            done += 1
            continue
        stem = dest.with_suffix("")
        try:
            got = comfy_client.fetch_from_history(SERVER, out_stem=stem, pid=it["pid"],
                                                  kinds=(it["kind"],))
            # normalise to the intended dest name/suffix
            g = got[0]
            if g != dest:
                g.rename(dest)
            print(f"fetched {it['name']} -> {dest.name}")
            done += 1
        except SystemExit as e:
            print(f"pending {it['name']} ({str(e)[:60]})")
            pending += 1
    print(f"\n{done} done, {pending} pending of {len(items)}")


if __name__ == "__main__":
    main()
