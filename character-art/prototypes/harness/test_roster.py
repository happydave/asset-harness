#!/usr/bin/env python3
"""Tests for roster loading. Plain `python3 test_roster.py`, no pytest."""
import sys, tempfile
from pathlib import Path
import roster as R

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond: FAILS.append(name)

CSV = """id,display_name,identity_features,tags,seed,tier,targets,notes
tiefling,Sera,horn pair;tail;red skin,1girl tiefling,303,repose,roll20;foundry_rings,from WI 1599
dragonborn,Vex,snout;scales;no human nose,1other dragonborn,404,repose,roll20,
halforc,Grum,tusk pair;jaw mass;green skin,1boy half-orc,202,lora,foundry,
nameless,Nobody,,1boy human,1,repose,roll20,deliberately missing features
badtier,Bad,horns,1boy,1,wizard,roll20,
badseed,Seedless,horns,1boy,notanumber,repose,roll20,
"""

def main():
    print("roster")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)/"roster.csv"; p.write_text(CSV, encoding="utf-8")
        load = R.load(p)

        ids = [c.id for c in load.characters]
        check("parses the well-formed rows", ids == ["tiefling","dragonborn","halforc","nameless"], ids)

        deliverable = [c.id for c in load.deliverable]
        check("a row with no identity_features is NOT deliverable",
              "nameless" not in deliverable and len(deliverable) == 3, deliverable)

        why = {cid: w for _, cid, w in load.rejected}
        check("rejects an unknown tier, naming it", "badtier" in why and "wizard" in why["badtier"], why)
        check("rejects a non-integer seed, naming it", "badseed" in why and "notanumber" in why["badseed"], why)
        check("one bad row does not abort the others", len(load.characters) == 4)

        t = load.characters[0]
        check("splits identity_features on ;", t.identity_features == ["horn pair","tail","red skin"], t.identity_features)
        check("splits targets on ;", t.targets == ["roll20","foundry_rings"], t.targets)
        check("preserves unknown columns rather than dropping them",
              t.extra.get("notes") == "from WI 1599", t.extra)
        check("defaults tier when absent", R.DEFAULT_TIER == "repose")

        rep = R.report(load)
        check("report names the non-deliverable row", "NOT DELIVERABLE" in rep and "nameless" in rep)

        # a roster missing a required column is a hard stop, not a silent empty batch
        bad = Path(td)/"bad.csv"; bad.write_text("id,display_name\nx,y\n", encoding="utf-8")
        try:
            R.load(bad); check("missing required column is a hard stop", False, "no SystemExit")
        except SystemExit as e:
            check("missing required column is a hard stop", "identity_features" in str(e), str(e))

    print()
    if FAILS: print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0

if __name__ == "__main__":
    sys.exit(main())
