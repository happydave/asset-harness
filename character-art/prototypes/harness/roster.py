#!/usr/bin/env python3
"""The roster: one CSV row per character.

That file is the campaign's source of truth — WI 1611 calls it "simultaneously the prompt source,
the campaign roster and the regeneration key, and more valuable than any individual image". This
module only loads and validates it; nothing here talks to ComfyUI.

The load-bearing column is `identity_features`. WI 1599 could score whether re-projection preserved
a dragonborn's snout only because the features were named *before* the images existed, and
design-character-art.md promotes that to the track's test oracle. A row without them cannot be
checked, so it is not deliverable — reported, not silently generated.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

#: Columns the batch reads. Unknown columns are preserved in `extra` rather than dropped, so the
#: roster can carry campaign notes the harness has no opinion about.
REQUIRED = ("id", "display_name", "identity_features", "tags")
LIST_SEP = ";"

TIERS = ("lora", "repose", "seed")
DEFAULT_TIER = "repose"


@dataclass
class Character:
    id: str
    display_name: str
    identity_features: list[str]
    tags: str
    seed: int = 0
    tier: str = DEFAULT_TIER
    targets: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def deliverable(self) -> bool:
        """A character with nothing named to preserve cannot be checked, so it is not deliverable."""
        return bool(self.identity_features)


@dataclass
class RosterLoad:
    characters: list[Character]
    rejected: list[tuple[int, str, str]]  # (line number, id, why)

    @property
    def deliverable(self) -> list[Character]:
        return [c for c in self.characters if c.deliverable]


def _split(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(LIST_SEP) if p.strip()]


def load(path) -> RosterLoad:
    """Load and validate a roster CSV. Never raises on a bad row — it reports it.

    A batch that aborts on one malformed row wastes every other character's GPU time, so a
    rejected row is carried in `rejected` and the rest proceed.
    """
    path = Path(path)
    characters: list[Character] = []
    rejected: list[tuple[int, str, str]] = []

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{path}: roster is missing required column(s): {', '.join(missing)}")

        for lineno, row in enumerate(reader, start=2):
            cid = (row.get("id") or "").strip()
            if not cid:
                rejected.append((lineno, "", "no id"))
                continue

            feats = _split(row.get("identity_features", ""))
            tier = (row.get("tier") or DEFAULT_TIER).strip() or DEFAULT_TIER
            if tier not in TIERS:
                rejected.append((lineno, cid, f"unknown tier {tier!r} (expected one of {TIERS})"))
                continue

            try:
                seed = int((row.get("seed") or "0").strip() or 0)
            except ValueError:
                rejected.append((lineno, cid, f"seed is not an integer: {row.get('seed')!r}"))
                continue

            known = set(REQUIRED) | {"seed", "tier", "targets"}
            characters.append(Character(
                id=cid,
                display_name=(row.get("display_name") or cid).strip(),
                identity_features=feats,
                tags=(row.get("tags") or "").strip(),
                seed=seed,
                tier=tier,
                targets=_split(row.get("targets", "")),
                extra={k: v for k, v in row.items() if k not in known and k is not None},
            ))

    return RosterLoad(characters=characters, rejected=rejected)


def report(load_result: RosterLoad) -> str:
    """A human-readable summary — what will run, what will not, and why."""
    lines = []
    for c in load_result.characters:
        if c.deliverable:
            lines.append(f"  {c.id:<14} tier={c.tier:<7} features={len(c.identity_features)} "
                         f"seed={c.seed}")
        else:
            lines.append(f"  {c.id:<14} NOT DELIVERABLE — no identity_features; "
                         f"nothing to check preservation against")
    for lineno, cid, why in load_result.rejected:
        lines.append(f"  line {lineno} {cid or '(no id)'}: REJECTED — {why}")
    return "\n".join(lines)
