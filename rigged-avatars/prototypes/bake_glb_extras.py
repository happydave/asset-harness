#!/usr/bin/env python3
"""Bake per-animation `extras` into robot.glb (+ debug/robot.gltf) from robot_manifest.json.

Pure python3 — no Blender, no deps. glTF has a spec-valid `extras` field on every object; Blender's
exporter does not reliably emit it onto *animations*, so we inject it here deterministically. Onto
each glTF animation we add {loop, fps, frameStart, frameEnd, durationSec, events}; at the document
root we add a provenance `extras`. The `robot_manifest.json` sidecar stays the authoritative,
engine-friendly copy (load it beside the glb, key clips by name) — these embedded extras are the
travels-with-the-asset mirror for glTF-aware tooling (viewers, GLB Studio, DCC round-trips).

`durationSec` is read from the animation's own input-sampler accessor max (the engine's true clip
length), not recomputed from fps — so the embedded number matches what an importer sees.

    python3 bake_glb_extras.py --dir out --name robot
    python3 bake_glb_extras.py --dir out --name corn
"""
import json, struct, sys
from pathlib import Path

argv = sys.argv[1:]
DIR = Path(argv[argv.index("--dir") + 1]) if "--dir" in argv else Path("out")
NAME = argv[argv.index("--name") + 1] if "--name" in argv else "robot"
MERGE = argv[argv.index("--merge") + 1] if "--merge" in argv else None
GLB = DIR / f"{NAME}.glb"
GLTF = DIR / "debug" / f"{NAME}.gltf"
MANIFEST = DIR / f"{NAME}_manifest.json"


def clip_extras(meta, j, anim):
    # True clip time axis, straight from the animation's input-sampler accessors (seconds).
    min_t, max_t = None, 0.0
    for s in anim.get("samplers", []):
        acc = j["accessors"][s["input"]]
        if acc.get("max"):
            max_t = max(max_t, float(acc["max"][0]))
        if acc.get("min"):
            m = float(acc["min"][0])
            min_t = m if min_t is None else min(min_t, m)
    min_t = 0.0 if min_t is None else min_t
    # Resolve each event's phase to an exact timeSec on that axis.
    events = []
    for e in meta.get("events", []):
        ev = dict(e)
        if "phase" in e:
            ev["timeSec"] = round(min_t + e["phase"] * (max_t - min_t), 5)
        events.append(ev)
    ex = {
        "loop": meta.get("loop", True),
        "oneShot": meta.get("one_shot"),
        "fps": meta.get("fps"),
        "frameStart": meta.get("frame_start"),
        "frameEnd": meta.get("frame_end"),
        "durationSec": round(max_t, 5),
        "events": events,
    }
    return {k: v for k, v in ex.items() if v is not None}


def provenance(man):
    keep = ("asset", "generator_script", "license", "frame", "bind", "failure_transform")
    p = {"generator": "asset-harness/rigged-avatars"}
    p.update({k: man[k] for k in keep if k in man})
    return p


def merge_animations(j, name):
    """Collapse many per-object animations (e.g. a glTF SCENE/per-object export) into ONE named clip:
    union the samplers (re-offsetting channel sampler indices; accessor indices are global and stay)."""
    anims = j.get("animations", [])
    if len(anims) <= 1:
        if anims:
            anims[0]["name"] = name
        return
    samplers, channels = [], []
    for a in anims:
        base = len(samplers)
        samplers.extend(a.get("samplers", []))
        for ch in a.get("channels", []):
            channels.append({"sampler": ch["sampler"] + base, "target": ch["target"]})
    j["animations"] = [{"name": name, "samplers": samplers, "channels": channels}]


def inject(j, man):
    if MERGE:
        merge_animations(j, MERGE)
    clips = man.get("clips", {})
    anims = j.get("animations", [])
    # SCENE-mode export can leave one unnamed/oddly-named clip; if it's 1:1 with the manifest, adopt
    # the manifest's clip name so `named_animations[...]` lookups and extras-matching work.
    if len(anims) == 1 and len(clips) == 1:
        only = next(iter(clips))
        if anims[0].get("name") != only:
            anims[0]["name"] = only
    injected = []
    for anim in anims:
        name = anim.get("name", "")
        anim["extras"] = clip_extras(clips.get(name, {}), j, anim)
        injected.append((name, anim["extras"]))
    j.setdefault("extras", {})["asset_harness"] = provenance(man)
    return injected


def read_glb(path):
    d = path.read_bytes()
    if d[:4] != b"glTF":
        raise ValueError("not a GLB")
    total = struct.unpack("<I", d[8:12])[0]
    off, js, binc = 12, None, None
    while off < total:
        (clen,) = struct.unpack("<I", d[off:off + 4])
        ctype = d[off + 4:off + 8]
        cdata = d[off + 8:off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(cdata)
        elif ctype == b"BIN\x00":
            binc = cdata          # preserved verbatim (keeps its own padding)
        off += 8 + clen
    return js, binc


def write_glb(path, j, binc):
    js = json.dumps(j, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)                       # pad JSON chunk with spaces
    out = bytearray(b"glTF")
    total = 12 + 8 + len(js) + (8 + len(binc) if binc is not None else 0)
    out += struct.pack("<II", 2, total)
    out += struct.pack("<I", len(js)) + b"JSON" + js
    if binc is not None:
        out += struct.pack("<I", len(binc)) + b"BIN\x00" + binc
    path.write_bytes(out)


def main():
    man = json.loads(MANIFEST.read_text())
    # GLB
    j, binc = read_glb(GLB)
    injected = inject(j, man)
    write_glb(GLB, j, binc)
    print(f"{GLB.name}: injected extras on {len(injected)} animations + root provenance")
    for name, ex in injected:
        print(f"  {name}: loop={ex.get('loop')} fps={ex.get('fps')} "
              f"dur={ex.get('durationSec')}s events={len(ex.get('events', []))}")
    # GLTF (separate) — standalone JSON, external .bin untouched
    if GLTF.exists():
        gj = json.loads(GLTF.read_text())
        inject(gj, man)
        GLTF.write_text(json.dumps(gj, indent=2))
        print(f"{GLTF.name}: extras injected")


if __name__ == "__main__":
    main()
