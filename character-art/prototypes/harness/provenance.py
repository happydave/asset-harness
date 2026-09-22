#!/usr/bin/env python3
"""The master-PNG provenance guard.

A master PNG carries its own ComfyUI workflow in its `tEXt` chunks, so destroying one destroys the
only record of how it was made.

`may_write` decides and touches nothing; `write_guarded` is the only writer and asks first. Keeping
the decision out of the writer is what lets the test hand real master paths to the predicate
without ever putting a master in front of the operation — inlining the check would look like a
simplification and would remove that.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Masters live here, relative to a character's output root, and carry this suffix. Two independent
#: markers rather than one: a derivative accidentally routed into masters/ is refused even if it is
#: named like a derivative, and a file named like a master is refused even outside masters/.
MASTERS_DIR = "masters"
MASTER_SUFFIX = ".master.png"

ROLE_MASTER = "master"


@dataclass(frozen=True)
class Verdict:
    """Why a write was permitted or refused. The reason is part of the answer, not a log line."""
    permitted: bool
    reason: str

    def __bool__(self) -> bool:
        return self.permitted


def is_master_path(dest: Path) -> bool:
    """True when `dest` names a master by either marker. Pure."""
    dest = Path(dest)
    return dest.name.endswith(MASTER_SUFFIX) or MASTERS_DIR in dest.parts


def may_write(dest, role: str) -> Verdict:
    """Decide whether writing `role` to `dest` is permitted. Reads the filesystem; writes nothing.

    The rules, in the order they are applied:

    1. An **existing** master is never overwritten, whatever the role. This is the invariant.
    2. A non-master role may not write to a master path even when nothing is there yet, because
       that is how a derivative silently becomes tomorrow's unoverwritable master.
    3. Anything else is a derivative going to its own path, or a new master: permitted.
    """
    dest = Path(dest)
    master_path = is_master_path(dest)

    if master_path and dest.exists():
        return Verdict(False, f"{dest} is an existing master; masters are never overwritten")
    if master_path and role != ROLE_MASTER:
        return Verdict(False, f"role {role!r} may not write to the master path {dest}")
    if master_path:
        return Verdict(True, f"creating new master {dest}")
    return Verdict(True, f"derivative {role!r} -> {dest}")


def write_guarded(dest, role: str, payload: bytes) -> Path:
    """Write `payload` to `dest`, but only if `may_write` permits it.

    The guarded act lives here and nowhere else; every other module routes through it.
    """
    dest = Path(dest)
    verdict = may_write(dest, role)
    if not verdict:
        raise PermissionError(f"refused: {verdict.reason}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return dest


def master_path(root, character_id: str) -> Path:
    """Where a character's master lives. One place decides this, so the guard and the writers agree."""
    return Path(root) / MASTERS_DIR / f"{character_id}{MASTER_SUFFIX}"


def derivative_path(root, character_id: str, stage: str, ext: str = "png") -> Path:
    """Where a named derivative stage lives — always outside masters/."""
    return Path(root) / "derivatives" / character_id / f"{character_id}.{stage}.{ext}"


def versioned(dest) -> Path:
    """`dest` if nothing is there, else the first free `<stem>.<n><suffix>` from n = 2.

    A re-run over an existing root writes beside the earlier run's artifacts rather than over them,
    so the earlier `records.json` keeps describing files that still have the content it recorded.
    Reads the filesystem; writes nothing. Never used for a master -- a master is reused, not
    versioned.
    """
    dest = Path(dest)
    if not dest.exists():
        return dest
    n = 2
    while True:
        candidate = dest.with_name(f"{dest.stem}.{n}{dest.suffix}")
        if not candidate.exists():
            return candidate
        n += 1
