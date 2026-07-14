"""Author sidecar manifests for the committed audio samples (Asset Studio contracts v2).

Run from the repo root:  python3 audio/prototypes/write_audio_manifests.py

Until now the audio track's per-clip metadata existed *only* as Python literals inside the
generator scripts (`SFX[]` in sfx/generate_sfx.py, `TRACKS[]` in music/generate_music.py) and
was lost at generation time — the gap recorded in
findings/2026-06-23-sfx-stable-audio-3.md ("Fold a small SFX manifest (name → seconds/seed/
loop/lufs)"). This writes one `audio_manifest.json` per committed sample directory, each a
valid `audio-collection` catalog entry, so the clips are catalogable like every other track.

The generator literals are read with `ast` rather than imported: both scripts `import requests`
at module scope, and harness-side Python is stdlib-only by convention (Asset Studio WI 902).
Durations / sample rates / channels are probed from the shipped .ogg files with `ffprobe`
(already a dependency — optimize_audio.py uses ffmpeg), so the manifest describes the files as
they actually ship (post-crossfade), not the pre-post generation length.

Idempotent: re-running rewrites byte-identical manifests.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_VERSION = 2

# The model lanes differ, and the license record is where that must show up (Asset Studio
# design: commercial-in-game and standalone-redistributable are independent axes).
#
# README: "**SFX** → **Stable Audio 3 Medium** (Stability Community License; ...). Revenue-gated
# <$1M + bundles T5Gemma/Gemma terms"  →  usable in our games, NOT redistributable as a pack.
SFX_LICENSE = {
    "status": "conditional",
    "commercial_in_game": True,
    "standalone_redistributable": False,
    "source": {
        "kind": "provider-tos",
        "note": ("Stable Audio 3 Medium under the Stability Community License: commercial use "
                 "revenue-gated under $1M/yr and bundling T5Gemma/Gemma terms; cleared for "
                 "in-game use, not for standalone redistribution"),
    },
}
# README: "**Music/ambient** → **ACE-Step 1.5** (**MIT**; runs on AMD). Instrumental/ambient only
# for shipped assets" — the instrumental constraint is satisfied by these beds (no vocals).
MUSIC_LICENSE = {
    "status": "clean",
    "commercial_in_game": True,
    "standalone_redistributable": True,
    "source": {
        "kind": "local-generation",
        "note": "ACE-Step 1.5 (MIT); instrumental/ambient only, per the track's shipping rule",
    },
}

# (sample dir, entry id, source generator, literal name, license lane)
COLLECTIONS = [
    ("audio/findings/samples-2026-06-23", "dwa-sfx",
     "audio/prototypes/sfx/generate_sfx.py", "SFX", SFX_LICENSE),
    ("audio/findings/samples-2026-06-24", "dwa-thruster-set",
     "audio/prototypes/sfx/generate_sfx.py", "SFX", SFX_LICENSE),
    ("audio/findings/samples-2026-06-24-music", "ambient-beds",
     "audio/prototypes/music/generate_music.py", "TRACKS", MUSIC_LICENSE),
]


def read_literal(script_rel, name):
    """The generator's list-of-dicts literal, without importing the module (it pulls in
    `requests`). ast.literal_eval keeps this to data — no code from the script runs."""
    tree = ast.parse((ROOT / script_rel).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise SystemExit("%s: no top-level %s literal found" % (script_rel, name))


def probe(path):
    """duration / sample rate / channels of the shipped file (ffprobe, first audio stream)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels:format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return {
        "duration_s": round(float(data["format"]["duration"]), 3),
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
    }


def clip_for(path, spec):
    """One clip record: the generator's own parameters + what the shipped file measures.
    `seconds` is deliberately not copied — it is the pre-post generation length, and
    duration_s (probed) is the truth about the file being catalogued."""
    clip = {"name": path.stem, "file": path.name, "format": path.suffix.lstrip(".")}
    clip.update(probe(path))
    if spec is not None:
        clip["loop"] = bool(spec.get("loop", False))
        for source_key, clip_key in (("seed", "seed"), ("lufs", "lufs_target"),
                                     ("bpm", "bpm"), ("key", "key"), ("tags", "tags"),
                                     ("prompt", "prompt")):
            if source_key in spec:
                clip[clip_key] = spec[source_key]
    return clip


def main():
    status = 0
    for rel, entry_id, script, literal, license_record in COLLECTIONS:
        directory = ROOT / rel
        if not directory.is_dir():
            print("MISSING %s" % directory)
            status = 1
            continue

        specs = {s["name"]: s for s in read_literal(script, literal)}
        # Music beds are looped in post (generate-long + crossfade) — the TRACKS literal has no
        # `loop` key, but every shipped bed is a seamless whole-file loop.
        loop_default = literal == "TRACKS"

        clips = []
        for path in sorted(directory.glob("*.ogg")):
            spec = specs.get(path.stem)
            if spec is None:
                print("WARN %s: no %s entry named %s — cataloguing file facts only"
                      % (rel, literal, path.stem))
            clip = clip_for(path, spec)
            if loop_default:
                clip["loop"] = True
            clips.append(clip)

        if not clips:
            print("MISSING %s: no .ogg samples" % rel)
            status = 1
            continue

        doc = {
            "schema_version": SCHEMA_VERSION,
            "id": entry_id,
            "class": "audio-collection",
            "license_record": license_record,
            "provenance": {
                "source_of_truth": "manual-import",
                "generator_script": Path(script).name,
            },
            "clips": clips,
        }
        out = directory / "audio_manifest.json"
        out.write_text(json.dumps(doc, indent=2) + "\n")
        print("wrote %s (%d clips)" % (out.relative_to(ROOT), len(clips)))
    return status


if __name__ == "__main__":
    sys.exit(main())
