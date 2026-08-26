#!/usr/bin/env python3
"""Re-pick and staleness audit over a manifest's candidate layer (WI 1175).

The companion tool to `manifest.py`'s candidate substrate. Two modes:

  pick   -- promote a DIFFERENT already-recorded candidate: the former chosen becomes
            `passed-over`, the target becomes `chosen`, the shot's `asset` (or the manifest's
            `audio` for --song) is updated, and the superseded pick is appended to the pick
            history with the picker, reason, and date. Re-picking never regenerates anything:
            a target that is not in the recorded candidate set is refused, as is one whose file
            is gone from disk. A currently-`culled` target is refused unless --allow-culled --
            picking past a machine gate should be deliberate, and with the flag the override is
            still recorded like any pick (overrides are measurements, not errors). On any
            refusal the manifest file is untouched; the new content is validated before the
            write. After a successful pick the audit runs and prints, so the blast radius of
            the change is visible at the moment it is made.

  audit  -- derive staleness: list every CHOSEN candidate whose recorded provenance no longer
            matches the manifest's current state (a still whose shot prompt/lines moved on, a
            clip whose source shot now shows a different still). Nothing is stored -- staleness
            is always derived, so it cannot drift out of sync. Exit 0 when clean, 1 when stale
            records exist, so a driver can gate on it. Non-chosen candidates are not audited:
            staleness matters for what is on screen; a stale survivor is simply never re-picked
            into.

Pure stdlib, GPU-free, like everything else in the schema layer.

  python3 repick.py pick  MANIFEST --shot 3 --to shot3_seed7.png --by owner --reason "warmer light"
  python3 repick.py pick  MANIFEST --song --to song_seed2.flac --by owner --reason "tighter chorus"
  python3 repick.py audit MANIFEST
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import manifest as M


class RepickError(ValueError):
    """A pick request that must be refused. The manifest on disk is left untouched."""


def audit(m: M.Manifest) -> list[dict]:
    """Every chosen candidate whose provenance no longer matches current upstream choices.

    Comparisons are evidence-driven: a provenance key that was never recorded is skipped, not
    treated as a mismatch -- the audit acts only on what generation actually wrote down.
    Each finding is {where, field, recorded, current}.
    """
    stale: list[dict] = []

    def compare(where: str, prov: dict, checks: list[tuple[str, object]]) -> None:
        for key, current in checks:
            if key in prov and prov[key] != current:
                stale.append({"where": where, "field": key,
                              "recorded": prov[key], "current": current})

    for s in m.shots:
        chosen = next((c for c in s.candidates if c.verdict == "chosen"), None)
        if chosen is None:
            continue
        if s.kind == "video":
            src = chosen.provenance.get("source_shot")
            # range-guarded rather than assumed valid: audit may run on a manifest that has not
            # been through validate(), and a dangling index should read as "no evidence", not crash
            if (isinstance(src, int) and 0 <= src < len(m.shots)
                    and "source_still" in chosen.provenance):
                compare(f"shot {s.index} clip", chosen.provenance,
                        [("source_still", m.shots[src].asset)])
        else:
            compare(f"shot {s.index} still", chosen.provenance,
                    [("prompt", s.prompt), ("lines", s.lines)])
    return stale


def repick(m: M.Manifest, *, shot: int | None, song: bool, to_asset: str, by: str, reason: str,
           manifest_dir: Path, allow_culled: bool = False,
           date: str | None = None) -> M.Manifest:
    """Apply the re-pick to `m` in place and return it. Raises RepickError on any refusal."""
    if song:
        where, cands, pick, promoted = "song", m.song_candidates, m.song_pick, m.audio
    else:
        if shot is None or not (0 <= shot < len(m.shots)):
            raise RepickError(f"no shot {shot} in a {len(m.shots)}-shot manifest")
        s = m.shots[shot]
        where, cands, pick, promoted = f"shot {shot}", s.candidates, s.pick, s.asset
    if not cands:
        raise RepickError(f"{where} has no recorded candidates -- re-pick never regenerates; "
                          f"record candidates at generation time first")
    target = next((c for c in cands if c.asset == to_asset), None)
    if target is None:
        raise RepickError(f"{where}: {to_asset!r} is not a recorded candidate "
                          f"(have: {', '.join(c.asset for c in cands)})")
    if target.asset == promoted and target.verdict == "chosen":
        raise RepickError(f"{where}: {to_asset!r} is already the chosen candidate")
    if not (manifest_dir / target.asset).resolve().is_file():
        raise RepickError(f"{where}: candidate file missing on disk: "
                          f"{(manifest_dir / target.asset).resolve()}")
    if target.verdict == "culled" and not allow_culled:
        raise RepickError(f"{where}: {to_asset!r} was culled by {target.culled_by!r}; "
                          f"pass --allow-culled to override the gate deliberately")

    when = date or datetime.date.today().isoformat()
    for c in cands:
        if c.verdict == "chosen":
            c.verdict = "passed-over"
    target.verdict = "chosen"
    target.culled_by = ""
    new_pick = M.Pick(picked_by=by, reason=reason,
                      history=list(pick.history) if pick else [])
    if pick is not None:
        new_pick.history.append({"asset": promoted, "picked_by": pick.picked_by,
                                 "reason": pick.reason, "date": when})
    if song:
        m.audio = to_asset
        m.song_pick = new_pick
    else:
        s.asset = to_asset
        s.pick = new_pick
    return m


def _cmd_pick(args: argparse.Namespace) -> int:
    path = Path(args.manifest).resolve()
    m = M.from_json(path.read_text())
    try:
        repick(m, shot=args.shot, song=args.song, to_asset=args.to, by=args.by,
               reason=args.reason, manifest_dir=path.parent, allow_culled=args.allow_culled,
               date=args.date)
        text = M.to_json(m, manifest_dir=path.parent)  # validate BEFORE touching the file
    except (RepickError, M.ManifestError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    path.write_text(text)
    where = "song" if args.song else f"shot {args.shot}"
    print(f"-> {path.name}: {where} now {args.to} (picked_by {args.by})")
    stale = audit(m)
    _print_audit(stale)
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    m = M.from_json(Path(args.manifest).resolve().read_text())
    stale = audit(m)
    _print_audit(stale)
    return 1 if stale else 0


def _print_audit(stale: list[dict]) -> None:
    if not stale:
        print("no stale records: every chosen candidate's provenance matches current choices")
        return
    print(f"{len(stale)} stale record(s) -- provenance no longer matches current choices:")
    for r in stale:
        print(f"   {r['where']}: {r['field']} was {r['recorded']!r}, now {r['current']!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("pick", help="promote another recorded candidate")
    p.add_argument("manifest", help="path to the shot-list manifest JSON")
    tgt = p.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--shot", type=int, help="shot index to re-pick")
    tgt.add_argument("--song", action="store_true", help="re-pick the song")
    p.add_argument("--to", required=True, help="asset of the candidate to promote")
    p.add_argument("--by", required=True, choices=list(M.PICKERS), help="who is picking")
    p.add_argument("--reason", default="", help="why (recorded in the pick; feeds the judge rubric)")
    p.add_argument("--allow-culled", action="store_true",
                   help="deliberately promote a candidate a machine gate rejected")
    p.add_argument("--date", default=None, help=argparse.SUPPRESS)  # tests inject a fixed date

    a = sub.add_parser("audit", help="list records whose provenance is stale")
    a.add_argument("manifest", help="path to the shot-list manifest JSON")

    args = ap.parse_args()
    sys.exit(_cmd_pick(args) if args.mode == "pick" else _cmd_audit(args))


if __name__ == "__main__":
    main()
