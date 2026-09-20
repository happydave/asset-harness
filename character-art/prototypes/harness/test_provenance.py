#!/usr/bin/env python3
"""Tests for the master-PNG guard. Plain `python3 test_provenance.py`, no pytest.

Same convention as music-video/prototypes/test_manifest.py: exits non-zero on failure so it gates
without a dependency.

The point of this file is the dangerous arguments. Per the workflow's destructive-operation
directive, `may_write` is asked about real master paths directly; `write_guarded` is only ever
handed paths this test created inside a temporary directory. A test that proved the guard by
calling the writer on a live master would be exactly the mistake the directive was written after.
"""
import sys
import tempfile
from pathlib import Path

import provenance as P

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def main():
    print("provenance guard")

    # --- the predicate, asked about dangerous arguments; nothing is written ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        existing = P.master_path(root, "tiefling")
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"pretend this is a master carrying its own workflow")

        v = P.may_write(existing, P.ROLE_MASTER)
        check("refuses overwriting an existing master, even as role=master",
              not v.permitted, v.reason)

        v = P.may_write(existing, "finished")
        check("refuses overwriting an existing master as a derivative role",
              not v.permitted, v.reason)

        fresh = P.master_path(root, "dragonborn")
        v = P.may_write(fresh, P.ROLE_MASTER)
        check("permits creating a master that does not exist yet", v.permitted, v.reason)

        v = P.may_write(fresh, "finished")
        check("refuses a derivative role aimed at a master path even when absent",
              not v.permitted, v.reason)

        # Both markers are load-bearing and are tested separately.
        v = P.may_write(root / "derivatives" / "x" / "y.master.png", "finished")
        check("refuses on the suffix marker alone (outside masters/)", not v.permitted, v.reason)
        v = P.may_write(root / P.MASTERS_DIR / "stray.png", "finished")
        check("refuses on the directory marker alone (no .master.png suffix)",
              not v.permitted, v.reason)

        d = P.derivative_path(root, "tiefling", "finished")
        v = P.may_write(d, "finished")
        check("permits a derivative to its own path", v.permitted, v.reason)

        # The predicate must not have created, removed or altered anything.
        check("predicate wrote nothing: existing master untouched",
              existing.read_bytes().startswith(b"pretend"))
        check("predicate wrote nothing: absent master still absent", not fresh.exists())
        check("predicate wrote nothing: derivative still absent", not d.exists())

    # --- the writer, on arguments this test created ---
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = P.master_path(root, "halforc")
        P.write_guarded(m, P.ROLE_MASTER, b"first write")
        check("writer creates a new master", m.read_bytes() == b"first write")

        try:
            P.write_guarded(m, P.ROLE_MASTER, b"second write")
            check("writer refuses to overwrite a master", False, "no PermissionError raised")
        except PermissionError:
            check("writer refuses to overwrite a master", True)
        check("master content survived the refused overwrite", m.read_bytes() == b"first write")

        d = P.derivative_path(root, "halforc", "token")
        P.write_guarded(d, "token", b"derivative")
        check("writer writes a derivative", d.read_bytes() == b"derivative")
        check("derivative is not inside masters/", P.MASTERS_DIR not in d.parts)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
