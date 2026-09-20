#!/usr/bin/env python3
"""VTT token export.

The specs are the consumers', not ours (WI 1591 round 3, carried into WI 1611):

  * Roll20  — 280x280 PNG (70 px/square x 4)
  * Foundry — 400x400 WebP de facto; **512x512 minimum** where dynamic token rings are in use,
              and **no baked border** in that case, because the ring is drawn by the VTT and a
              baked one shows up as a double ring.

Every export is a derivative and goes through the provenance guard. The WebP path matters twice
over: WebP strips the PNG `tEXt` chunks that carry the workflow, so a token can never stand in for
its master.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

import provenance as P


@dataclass(frozen=True)
class TokenSpec:
    name: str
    size: int
    fmt: str          # PIL format
    ext: str
    rings: bool = False   # when True: no baked border, and the size floor applies


ROLL20 = TokenSpec("roll20", 280, "PNG", "png")
FOUNDRY = TokenSpec("foundry", 400, "WEBP", "webp")
FOUNDRY_RINGS = TokenSpec("foundry_rings", 512, "WEBP", "webp", rings=True)

SPECS = {s.name: s for s in (ROLL20, FOUNDRY, FOUNDRY_RINGS)}


def render_token(image: Image.Image, spec: TokenSpec) -> bytes:
    """Square-crop, resize to the spec and encode. Never composites a border.

    No border is drawn in any path, not only the ring path: a baked border cannot be removed
    downstream, and the VTT draws its own.
    """
    img = image.convert("RGBA")
    side = min(img.size)
    left = (img.width - side) // 2
    top = 0 if img.height <= side else (img.height - side) // 4  # bias up: heads beat feet
    img = img.crop((left, top, left + side, top + side)).resize(
        (spec.size, spec.size), Image.LANCZOS)

    buf = io.BytesIO()
    if spec.fmt == "WEBP":
        img.save(buf, format="WEBP", lossless=True, quality=100)
    else:
        img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def export(image: Image.Image, root, character_id: str, target_names) -> dict[str, Path]:
    """Export the requested targets. Returns {target name: path written}.

    An unknown target is refused by name rather than silently skipped — the roster asked for
    something the harness cannot produce, and the operator needs to know which.
    """
    written: dict[str, Path] = {}
    unknown = [t for t in target_names if t not in SPECS]
    if unknown:
        raise ValueError(f"unknown delivery target(s): {', '.join(unknown)}; "
                         f"known: {', '.join(sorted(SPECS))}")

    for name in target_names:
        spec = SPECS[name]
        dest = P.derivative_path(root, character_id, f"token.{spec.name}", spec.ext)
        written[name] = P.write_guarded(dest, f"token:{spec.name}",
                                        render_token(image, spec))
    return written
