#!/usr/bin/env python3
"""Author the concrete Clamor lobby-loop manifest and its assets (the WI 1004 skeleton driver).

This is the *authored* half of the track -- the creative decisions the pure renderer (`render.py`)
must not contain: the 8-shot cut, each shot's image prompt and Ken-Burns move, and which shot is the
hero video. It:

  1. loads the WI 1001 post-hoc timeline and partitions it into 8 shots (2 lyric lines each);
  2. fills each shot's creative fields from SPECS below;
  3. materialises each shot's asset under <build>/assets/ -- reuse a vetted still, generate a new
     Z-Image still on ai2, or interpolate the existing WI 1018 hero clip to the timeline fps;
  4. copies the song in and emits the committed manifest JSON (validated: assets must exist).

Idempotent: an asset already on disk is left alone, so "regenerate shot 5" is `rm assets/shot05.png`
then re-run. Generation is remote (ai2 Z-Image); everything else is local. Stdlib + requests + ffmpeg.

Prompt hygiene per ../license-lane.md: no franchise, artist, or real-person names; lyrics are WI 1001's
(already cleared). House style matches the two committed WI 1018 stills.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import comfy_client
import generate_still as gs
import interpolate
import manifest as M
import render as R
import timeline as T

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
BUILD = OUT / "lobby"
ASSETS = BUILD / "assets"
SERVER = "http://ai2:8188"

SONG = OUT / "clamor_hold_the_line_seed701.flac"
TIMELINE = OUT / "clamor_hold_the_line_seed701_posthoc.timeline.json"
VETTED = HERE.parent / "findings" / "samples-2026-07-23-wan-quality"

STYLE = ("painterly tabletop RPG concept art, dramatic volumetric light, warm lantern glow against "
         "cool blue shadows, cinematic wide establishing shot, richly detailed, muted desaturated "
         "palette, moody atmospheric")

# One spec per shot (index 0..7). `source` is reuse:<file> | gen:<seed> | hero:<clip>.
SPECS = [
    # 0 verse -- "Six of us went out at first light" -- the party sets out
    dict(kind="kenburns", kb=dict(zoom="in", pan="c"),
         source=f"reuse:{VETTED/'still_character_1280x720.png'}",
         prompt="a lone survivor scavenger setting out through a ruined overgrown city street at first "
                "light, worn leather armor and a heavy backpack, alert wary posture, " + STYLE),
    # 1 verse -- "The colony is waiting on the far side / of a city that has forgotten how to make a sound"
    dict(kind="kenburns", kb=dict(zoom="none", pan="r"), source="gen:101",
         prompt="a vast silent ruined city sprawling under a pale dawn sky, distant fortified colony "
                "with faint warm lights on the far horizon across the dead skyline, empty streets, "
                "utter stillness, " + STYLE),
    # 2 chorus -- "Hold the line, hold the line" -- HERO video
    dict(kind="video", kb={}, source=f"hero:{VETTED/'clip1_nolora_char_720p.mp4'}",
         prompt="[hero clip, WI 1018] a lone survivor scavenger holding ground in a ruined street at "
                "dusk, subtle motion; " + STYLE),
    # 3 chorus -- "One more street, one more night / we are going home tonight"
    dict(kind="kenburns", kb=dict(zoom="out", pan="c"), source="gen:102",
         prompt="a small band of survivors walking down a debris-strewn ruined avenue toward a warm "
                "distant glow of home, hopeful, backs to the camera, embers drifting, " + STYLE),
    # 4 verse -- "She has got the map and I have got the last flare / something in the stairwell"
    dict(kind="kenburns", kb=dict(zoom="in", pan="c"), source="gen:103",
         prompt="two survivors inside a dark ruined building, one holding up a burning red flare that "
                "casts dramatic light, a menacing shadow looming in a broken stairwell behind them, "
                "tense, " + STYLE),
    # 5 verse -- "Do not you make a sound out there / count it down and take them one by one"
    dict(kind="kenburns", kb=dict(zoom="in", pan="u"), source="gen:104",
         prompt="a survivor braced in a shattered doorway aiming a makeshift weapon into darkness, a "
                "single shambling undead silhouette approaching down the corridor, extreme tension, "
                "held breath, " + STYLE),
    # 6 chorus -- "Hold the line, hold the line" (reprise) -- the horde
    dict(kind="kenburns", kb=dict(zoom="in", pan="c"),
         source=f"reuse:{VETTED/'still_scene_1280x720.png'}",
         prompt="a menacing horde of shambling undead advancing down a ruined avenue toward a makeshift "
                "barricade at night, backlit by cold moonlight and drifting embers, " + STYLE),
    # 7 chorus -- "We are going home, we are going home tonight" (outro/resolve)
    dict(kind="kenburns", kb=dict(zoom="out", pan="c"), source="gen:105",
         prompt="dawn breaking over a ruined city as silhouetted survivors walk away toward a fortified "
                "colony gate glowing with warm safe light, hope and resolution, wide cinematic vista, "
                + STYLE),
]


def _materialise_asset(idx: int, spec: dict) -> str:
    """Ensure shot `idx`'s asset exists under ASSETS/; return its path relative to BUILD."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    src = spec["source"]
    if spec["kind"] == "video":
        dst = ASSETS / f"shot{idx:02d}.mp4"
        if not dst.exists():
            clip = Path(src.split("hero:", 1)[1])
            print(f"[shot {idx}] interpolate hero clip -> {R.FPS} fps")
            interpolate.interpolate(clip, dst, R.FPS)   # WI 1019 smoothness fix, at timeline fps
        return f"assets/{dst.name}"
    dst = ASSETS / f"shot{idx:02d}.png"
    if dst.exists():
        return f"assets/{dst.name}"
    if src.startswith("reuse:"):
        shutil.copyfile(Path(src.split("reuse:", 1)[1]), dst)
        print(f"[shot {idx}] reuse still -> {dst.name}")
    elif src.startswith("gen:"):
        seed = int(src.split("gen:", 1)[1])
        preset = gs.MODELS["base"]
        graph = gs.build_graph(spec["prompt"], gs.DEFAULT_NEGATIVE, width=1280, height=720,
                               seed=seed, model="base", steps=preset["steps"], cfg=preset["cfg"],
                               prefix=f"asset_harness/mv_lobby_shot{idx:02d}")
        print(f"[shot {idx}] generate Z-Image still (seed {seed}) on ai2 ...")
        got = comfy_client.run_job(SERVER, graph, dst.with_suffix(""), kinds=("images",),
                                   label=f"shot{idx:02d}")[0]
        if got != dst:
            shutil.move(str(got), str(dst))
    else:
        raise SystemExit(f"shot {idx}: unknown source {src!r}")
    return f"assets/{dst.name}"


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    tl = T.from_json(TIMELINE.read_text())
    shots = M.partition_shots(tl, [2] * 8)
    if len(shots) != len(SPECS):
        raise SystemExit(f"{len(shots)} shots but {len(SPECS)} specs")

    for i, (shot, spec) in enumerate(zip(shots, SPECS)):
        shot.kind = spec["kind"]
        shot.prompt = spec["prompt"]
        shot.kb = spec["kb"] or {"zoom": "none", "pan": "c"}
        shot.asset = _materialise_asset(i, spec)

    # song in, self-contained manifest dir
    song_rel = f"assets/{SONG.name}"
    if not (ASSETS / SONG.name).exists():
        shutil.copyfile(SONG, ASSETS / SONG.name)

    man = M.Manifest(
        audio=song_rel, duration=tl.duration,
        source_timeline=TIMELINE.name,
        shots=shots,
        notes=("WI 1004 walking skeleton; 8 shots x 2 lyric lines; hero video on chorus shot 2 "
               "(WI 1018 clip, interpolated); stills reuse 2 vetted WI 1018 frames + 5 Z-Image base."))
    out = BUILD / "clamor_lobby.manifest.json"
    M.write(man, out)
    print(f"-> {out}  ({len(shots)} shots, {tl.duration:.1f}s)")


if __name__ == "__main__":
    main()
