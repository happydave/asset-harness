#!/usr/bin/env python3
"""WI 1037: build the BLIND owner-ranking artifact from the generated candidates.

For each still shot group, tile its candidates into a labelled contact sheet (A,B,C,...) in filename
order, so the owner ranks by eye WITHOUT seeing the machine scores. Emit a ranking form to fill, and a
hidden label->filename key so the machine-vs-owner comparison can be computed afterwards. Songs are
listed for the owner to listen to and order.

Run with plain python3 (needs ffmpeg for the tiling), after fetch_all.py.
"""
import json
import string
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent / "outputs" / "spike1037"
STILLS = SPIKE / "stills"
SONGS = SPIKE / "songs"
SONG701 = HERE.parent / "outputs" / "clamor_hold_the_line_seed701.flac"
OUT = SPIKE / "ranking"


def tile(images, dst, cols):
    """Label each candidate with a letter (A, B, ...) and tile into one contact sheet."""
    inputs = []
    for p in images:
        inputs += ["-i", str(p)]
    n = len(images)
    rows = (n + cols - 1) // cols
    filt = []
    for i in range(n):
        letter = string.ascii_uppercase[i]
        filt.append(f"[{i}:v]scale=480:270,drawtext=text='{letter}':x=12:y=10:fontsize=40:"
                    f"fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=8[t{i}]")
    concat = "".join(f"[t{i}]" for i in range(n))
    filt.append(f"{concat}tile={cols}x{rows}:padding=8:color=gray[out]")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", ";".join(filt), "-map", "[out]", str(dst)], check=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    key = {}
    form = ["# WI 1037 blind ranking form\n",
            "Rank each group best -> worst using the tile letters. Do NOT look at machine_scores.json.\n"]

    # stills grouped by shot (exclude the sanity-floor from ranking; it is a separate control)
    groups = {}
    for p in sorted(STILLS.glob("*.png")):
        if p.name.startswith("sanity"):
            continue
        groups.setdefault(p.name.split("_seed")[0], []).append(p)
    for shot, paths in groups.items():
        paths = sorted(paths)
        key[shot] = {string.ascii_uppercase[i]: p.name for i, p in enumerate(paths)}
        tile(paths, OUT / f"{shot}_candidates.png", cols=len(paths))
        form.append(f"\n## {shot}  ({OUT.name}/{shot}_candidates.png) — {len(paths)} candidates "
                    f"{list(key[shot])}\n- Best -> worst: ______\n")

    # sanity control sheet (real best vs the off-brief image) — must the owner rank the off-brief last?
    sanity = sorted(STILLS.glob("sanity*.png"))
    if sanity and groups:
        first_shot = sorted(groups)[0]
        ctrl = [sorted(groups[first_shot])[0], sanity[0]]
        tile(ctrl, OUT / "sanity_control.png", cols=2)
        key["sanity_control"] = {"A": ctrl[0].name, "B": ctrl[1].name}
        form.append("\n## sanity_control (sanity_control.png) — A is a real candidate, B is off-brief.\n"
                    "- Which is better for a zombie-survival lobby (A/B)? ______\n")

    # songs
    songs = []
    if SONG701.exists():
        songs.append(("seed701", SONG701))
    for p in sorted(SONGS.glob("*.flac")):
        songs.append((p.stem.replace("clamor_hold_the_line_", ""), p))
    if songs:
        key["songs"] = {s[0]: str(s[1]) for s in songs}
        form.append("\n## songs — listen and order these files best -> worst:\n")
        for name, p in songs:
            form.append(f"  - {name}: {p}\n")
        form.append("- Best -> worst: ______\n")

    (OUT / "ranking_form.md").write_text("".join(form))
    (OUT / "_label_key.json").write_text(json.dumps(key, indent=2))  # de-anonymise AFTER ranking
    print(f"-> {OUT}/  (contact sheets + ranking_form.md; key hidden in _label_key.json)")


if __name__ == "__main__":
    main()
