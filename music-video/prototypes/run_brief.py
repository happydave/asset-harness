#!/usr/bin/env python3
"""The gated run driver (WI 1180): a brief file -> a rendered cut, through the candidate stages.

    python3 run_brief.py run inputs/clamor_hold_the_line.brief.json --out outputs/runs/clamor --mode provisional
    python3 run_brief.py run <brief> --out <dir>            # assisted (default): stops at each pick point
    python3 run_brief.py resume <brief> --out <dir>         # after filling a form, or after a repick.py

The brief is DATA (brief.schema.json; inputs/*.brief.json is a filled example): the song spec, a style
string, the shots (line counts, kinds, prompts, hero clips with motion prompts and a non-adjacent
source shot), an optional loop block and candidate counts. Nothing creative lives in this file.

Stages, each idempotent on disk and recorded in <out>/run.json so a run resumes from the first
incomplete one:

  preflight  preflight.py for the stages this brief needs; a FAIL stops the run
  song       select_song: sweep -> QC veto -> Audiobox CE -> machine-auto pick (no pick => stop)
  timeline   align_posthoc in the track venv against the brief's lyric sheet
  manifest   partition by the brief's line counts; placeholder assets; song block landed
  stills     cull_stills.sweep for still shots without candidates; assisted => WAIT on the form
             (exit 3); provisional => machine-provisional drafts
  clips      clip_candidates.sweep per video shot from its source shot's chosen still; same modes
  render     refused while any shot is on the placeholder; render.py (+ loop cut when a loop block)

Re-picks: `repick.py pick <manifest> --song ...` then `resume` re-derives the timeline and the
partition for the new song; shots whose lyric text is unchanged keep their candidates and picks
(their windows shift), others are reset and re-swept. `repick.py pick --shot N` then `resume`
re-renders and reports which shots' assets changed since the last render. The driver never restarts
or edits anything on ai2; it prints the restart-after-Wan reminder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import clip_candidates as clc
import cull_stills as cs
import manifest as M
import repick
import select_song as ss
import timeline as T

HERE = Path(__file__).resolve().parent
TRACK = HERE.parent
KINDS = ("still", "kenburns", "video")
STAGES = ("preflight", "song", "timeline", "manifest", "stills", "clips", "render")
PLACEHOLDER = "assets/placeholder.png"
EXIT_WAITING = 3
RESTART_REMINDER = "reminder: restart ComfyUI before an ACE-Step / Z-Image batch (ssh ai2 systemctl restart comfyui.service)"


class BriefError(ValueError):
    """The brief is malformed; nothing is run."""


class Stop(Exception):
    """The run stops here with a message and an exit code (the state file says why)."""
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# --- the brief ----------------------------------------------------------------------------------

def validate_brief(b: dict) -> None:
    for k in ("name", "song", "style", "shots"):
        if k not in b:
            raise BriefError(f"brief is missing {k!r}")
    for k in ("name", "seconds", "bpm", "key", "tags", "lyrics"):
        if k not in b["song"]:
            raise BriefError(f"brief.song is missing {k!r}")
    if not isinstance(b["shots"], list) or not b["shots"]:
        raise BriefError("brief.shots must be a non-empty list")
    n = len(b["shots"])
    for i, s in enumerate(b["shots"]):
        if s.get("kind") not in KINDS:
            raise BriefError(f"shots[{i}].kind must be one of {KINDS}, got {s.get('kind')!r}")
        if not isinstance(s.get("lines"), int) or s["lines"] < 1:
            raise BriefError(f"shots[{i}].lines must be an integer >= 1")
        if s["kind"] == "video":
            if not s.get("motion", "").strip():
                raise BriefError(f"shots[{i}] is a video shot without a motion prompt")
            src = s.get("source_shot")
            if not isinstance(src, int) or not (0 <= src < n):
                raise BriefError(f"shots[{i}].source_shot must index a shot (0..{n - 1})")
            if abs(src - i) == 1:
                raise BriefError(f"shots[{i}].source_shot {src} is adjacent: a clip must not sit next to its own "
                                 f"source still (WI 1160)")
            if b["shots"][src]["kind"] == "video":
                raise BriefError(f"shots[{i}].source_shot {src} is a video shot; it must be a still")
        elif not s.get("prompt", "").strip():
            raise BriefError(f"shots[{i}] ({s['kind']}) has no prompt")
        kb = s.get("kb") or {}
        if kb.get("zoom", "in") not in M.ZOOMS or kb.get("pan", "c") not in M.PANS:
            raise BriefError(f"shots[{i}].kb is not a Ken Burns move ({M.ZOOMS} / {M.PANS})")
    lp = b.get("loop")
    if lp is not None:
        if "length" not in lp or lp["length"] <= 0:
            raise BriefError("brief.loop.length must be a positive number")
        if lp.get("blend_at", "end") not in ("start", "end"):
            raise BriefError("brief.loop.blend_at must be 'start' or 'end'")
    c = b.get("candidates") or {}
    if not 1 <= c.get("stills_n", 5) <= cs.MAX_N or not 1 <= c.get("clips_n", 2) <= clc.MAX_N:
        raise BriefError(f"candidates.stills_n must be 1..{cs.MAX_N}, clips_n 1..{clc.MAX_N}")


def load_brief(path: Path) -> dict:
    b = json.loads(path.read_text())
    validate_brief(b)
    return b


def brief_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the default tools (the real stages); tests inject fakes with the same signatures -------------

class Tools:
    def __init__(self, server: str = ss.comfy_client.DEFAULT_SERVER):
        self.server = server

    def preflight(self, stages: list[str]) -> int:
        cmd = [sys.executable, str(HERE / "preflight.py"), "--server", self.server]
        for s in stages:
            cmd += ["--stage", s]
        return subprocess.run(cmd).returncode

    def song(self, spec: dict, seeds: list[int], out_dir: Path) -> dict:
        sweep = ss.generate_sweep(self.server, spec, seeds, out_dir, checkpoint=ss.gs.DEFAULT_CHECKPOINT,
                                  ceiling=ss.gs.CEILING_DBTP)
        scores = ss.score_audiobox([Path(v["path"]) for _, v in sorted(sweep.items())]) if sweep else {"error": "nothing to score"}
        rec = ss.build_record(spec, sweep, scores, out_dir=out_dir, checkpoint=ss.gs.DEFAULT_CHECKPOINT)
        (out_dir / f"{spec['name']}.song.json").write_text(json.dumps(rec, indent=2) + "\n")
        return rec

    def align(self, audio: Path, sheet: Path, out_stem: Path) -> Path:
        venv_py = TRACK / ".venv" / "bin" / "python"
        if not venv_py.exists():
            raise Stop(f"alignment venv missing at {venv_py}: cd {TRACK} && python3 -m venv .venv && "
                       f".venv/bin/pip install demucs whisperx  (or tap it: python3 tap_align.py --audio {audio} "
                       f"--lyrics {sheet} --out {out_stem})")
        r = subprocess.run([str(venv_py), str(HERE / "align_posthoc.py"), "--audio", str(audio),
                            "--lyrics", str(sheet), "--out", str(out_stem)], capture_output=True, text=True)
        if r.returncode != 0:
            raise Stop(f"alignment failed:\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        print(r.stdout.strip().splitlines()[-3:] and "\n".join(r.stdout.strip().splitlines()[-3:]))
        return out_stem.with_suffix(".timeline.json")

    def placeholder(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720",
                        "-frames:v", "1", str(path)], check=True)

    def still_sweep(self, manifest: Path, shots: list[int], n: int, seed_base: int, run_dir: Path) -> dict:
        return cs.sweep(manifest, shots=shots, n=n, seed_base=seed_base, model="base", run_dir=run_dir,
                        server=self.server)

    def still_apply_form(self, manifest: Path, run_dir: Path) -> dict:
        return cs.apply_form(manifest, run_dir)

    def still_provisional(self, manifest: Path) -> dict:
        return cs.provisional(manifest)

    def clip_sweep(self, manifest: Path, shot: int, source_shot: int, motion: str, n: int, seed_base: int,
                   run_dir: Path) -> dict:
        return clc.sweep(manifest, shot=shot, source_shot=source_shot, prompt=motion, n=n, seed_base=seed_base,
                         run_dir=run_dir, server=self.server)

    def clip_provisional(self, manifest: Path, shot: int) -> dict:
        return clc.provisional(manifest, shot)

    def render(self, manifest: Path, out: Path, workdir: Path) -> None:
        import render as R
        R.render(M.from_json(manifest.read_text()), manifest.parent, out, workdir)


# --- state ----------------------------------------------------------------------------------------

def load_state(out: Path) -> dict:
    p = out / "run.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"brief_sha256": None, "mode": None, "stages": {s: "pending" for s in STAGES},
            "song_chosen": None, "still_runs": [], "last_render_assets": {}, "notes": []}


def save_state(out: Path, st: dict) -> None:
    (out / "run.json").write_text(json.dumps(st, indent=2) + "\n")


# --- the run ----------------------------------------------------------------------------------------

def _shot_text(lines: list[dict]) -> str:
    return " | ".join(l["text"] for l in lines)


def build_shots(b: dict, tl: T.Timeline) -> list[M.Shot]:
    counts = [s["lines"] for s in b["shots"]]
    if sum(counts) != len(tl.lines):
        raise Stop(f"the brief's shots cover {sum(counts)} lines but the timeline has {len(tl.lines)}: "
                   f"fix the lyric sheet or the shots' line counts")
    shots = M.partition_shots(tl, counts)
    for shot, spec in zip(shots, b["shots"]):
        shot.kind = spec["kind"]
        if spec["kind"] == "video":
            shot.prompt = spec["motion"]
            shot.kb = {"zoom": "none", "pan": "c"}
        else:
            shot.prompt = f"{spec['prompt'].rstrip(', ')}, {b['style']}"
            shot.kb = dict(spec.get("kb") or {"zoom": "in", "pan": "c"})
        shot.asset = PLACEHOLDER
    return shots


LOW_CONFIDENCE_MAX = 0.25  # more than this fraction of lines interpolated => the edit would be wrong


def check_timeline_confidence(tl: T.Timeline, allow: bool, *, sheet: Path, audio: Path, out: Path) -> None:
    """An aligner that could not place a quarter of the lines produces windows the cut would be wrong
    with (the unmatched lines get squeezed into the tail). Stop in every mode unless overridden; the
    remedies are the owner's: tap the timeline, or re-pick the song and resume."""
    low = [l for l in tl.lines if l.confidence == "low"]
    if not low:
        return
    frac = len(low) / len(tl.lines)
    msg = (f"timeline: {len(low)}/{len(tl.lines)} lines are LOW confidence (interpolated): "
           + ", ".join(f"[{l.start:.1f}] {l.text[:30]}" for l in low[:4]) + (" …" if len(low) > 4 else ""))
    if frac > LOW_CONFIDENCE_MAX and not allow:
        raise Stop(msg + "\n  the aligner could not place these on this take; either tap them "
                   f"(music-video/.venv not needed): python3 tap_align.py --audio {audio} --lyrics {sheet} --out {out / 'timeline'}\n"
                   "  or re-pick the song: python3 repick.py pick <manifest> --song --to <asset> --by owner --reason '...' "
                   "then resume; or pass --allow-low-confidence to proceed anyway")
    print("warning: " + msg)


def carry_over(old: list[M.Shot], new: list[M.Shot]) -> list[int]:
    """Copy kind/prompt/kb/asset/candidates/pick from old shots whose lyric text matches; return the
    indices of new shots that were NOT carried (they need a sweep)."""
    # Match by position first (a repeated chorus gives two shots the same text), then by text among
    # the old shots not yet claimed, so a re-partition that shifts positions still finds its shot.
    unclaimed = list(old)
    reset = []
    for s in new:
        o = old[s.index] if s.index < len(old) and _shot_text(old[s.index].lines) == _shot_text(s.lines) else None
        if o is None:
            o = next((c for c in unclaimed if _shot_text(c.lines) == _shot_text(s.lines)), None)
        if o is not None and o in unclaimed:
            unclaimed.remove(o)
        if o is None or o.prompt != s.prompt or o.kind != s.kind:
            reset.append(s.index)
            continue
        s.asset, s.kb, s.candidates, s.pick = o.asset, o.kb, o.candidates, o.pick
        for c in s.candidates:
            if "lines" in c.provenance:
                c.provenance["lines"] = s.lines
    return reset


def run(brief_path: Path, out: Path, *, mode: str = "assisted", tools: Tools | None = None,
        accept_brief_change: bool = False, allow_low_confidence: bool = False) -> int:
    tools = tools or Tools()
    b = load_brief(brief_path)
    out.mkdir(parents=True, exist_ok=True)
    st = load_state(out)
    sha = brief_sha(brief_path)
    if st["brief_sha256"] and st["brief_sha256"] != sha and not accept_brief_change:
        raise Stop(f"the brief changed since this run started; start a new --out, or pass "
                   f"--accept-brief-change to re-derive from the manifest stage")
    brief_changed = bool(st["brief_sha256"]) and st["brief_sha256"] != sha
    st["brief_sha256"], st["mode"] = sha, mode
    cands = b.get("candidates") or {}
    song_seeds = cands.get("song_seeds", [701, 702, 703])
    stills_n, clips_n = cands.get("stills_n", 5), cands.get("clips_n", 2)
    seed_stills, seed_clips = cands.get("seed_base_stills", 41), cands.get("seed_base_clips", 901)
    has_video = any(s["kind"] == "video" for s in b["shots"])
    name = b["name"]
    manifest_path = out / f"{name}.manifest.json"
    song_dir, sheet = out / "song", out / f"{b['song']['name']}.lyrics.txt"
    tl_stem = out / "timeline"

    def done(stage):
        st["stages"][stage] = "done"; save_state(out, st)

    # 1. preflight
    if st["stages"]["preflight"] != "done":
        stages = ["song", "align", "still", "render"] + (["clip"] if has_video else [])
        if tools.preflight(stages) != 0:
            raise Stop("preflight FAILED -- fix what it names, then resume")
        done("preflight")

    # 2. song
    if st["stages"]["song"] != "done":
        rec = tools.song(b["song"], song_seeds, song_dir)
        if not rec["pick"]:
            code = ss.record_exit_code(rec)
            raise Stop(f"song stage: NO PICK -- {rec['no_pick_reason']}\n"
                       + ("pick by hand once the manifest exists is not possible yet; re-roll: edit candidates.song_seeds and resume"
                          if code == 2 else f"fix the scorer (see reason), or pick by hand after the manifest stage with repick.py --song"),
                       code)
        st["song_chosen"] = str((song_dir / rec["audio"]).resolve())
        done("song")
    song_audio = Path(st["song_chosen"])

    # 3. timeline
    if st["stages"]["timeline"] != "done":
        sheet.write_text(b["song"]["lyrics"])
        tools.align(song_audio, sheet, tl_stem)
        done("timeline")
    # A song re-pick (repick.py --song) shows up as the manifest's audio differing from the song the
    # timeline was derived for: re-derive the timeline FIRST, so every check below sees the new one.
    repicked = False
    if manifest_path.exists():
        current_audio = (out / M.from_json(manifest_path.read_text()).audio).resolve()
        if current_audio != song_audio.resolve():
            print(f"song re-picked -> {current_audio.name}: re-deriving timeline and partition")
            tools.align(current_audio, sheet, tl_stem)
            st["song_chosen"] = str(current_audio); save_state(out, st)
            song_audio, repicked = current_audio, True
    tl = T.from_json(tl_stem.with_suffix(".timeline.json").read_text())
    if len(tl.lines) != sum(s["lines"] for s in b["shots"]):
        raise Stop(f"the timeline has {len(tl.lines)} lines but the brief's shots cover "
                   f"{sum(s['lines'] for s in b['shots'])}")
    check_timeline_confidence(tl, allow_low_confidence, sheet=sheet, audio=song_audio, out=out)

    # 4. manifest
    if st["stages"]["manifest"] != "done":
        tools.placeholder(out / PLACEHOLDER)
        shots = build_shots(b, tl)
        lp = b.get("loop")
        loop = M.Loop(length=lp["length"], crossfade=lp.get("crossfade", 0.75), search=lp.get("search", 0.0),
                      blend_at=lp.get("blend_at", "end")) if lp else None
        m = M.Manifest(audio=str(song_audio), duration=tl.duration, source_timeline=tl_stem.with_suffix(".timeline.json").name,
                       shots=shots, loop=loop, notes=f"run_brief {name}; mode {mode}")
        m.audio = ss._rel(song_audio, out)
        M.write(m, manifest_path)
        rec = json.loads((song_dir / f"{b['song']['name']}.song.json").read_text())
        ss.apply_into(rec, manifest_path, song_dir)
        done("manifest")

    # re-pick / brief-change handling before the stage loop
    m = M.from_json(manifest_path.read_text())
    if repicked:
        new_shots = build_shots(b, tl)
        reset = carry_over(m.shots, new_shots)
        m.shots, m.duration, m.source_timeline = new_shots, tl.duration, tl_stem.with_suffix(".timeline.json").name
        st["notes"].append(f"song re-pick: shots reset {reset}")
        M.write(m, manifest_path)
        m = M.from_json(manifest_path.read_text())
    if brief_changed:
        new_shots = build_shots(b, tl)
        reset = carry_over(m.shots, new_shots)
        m.shots = new_shots
        st["notes"].append(f"brief change accepted: shots reset {reset}")
        M.write(m, manifest_path)
        m = M.from_json(manifest_path.read_text())
    stale = repick.audit(m)
    if stale:
        for f in stale:
            idx = int(f["where"].split()[1])
            s = m.shots[idx]
            s.asset, s.candidates, s.pick = PLACEHOLDER, [], None
        st["notes"].append(f"stale picks reset: {sorted({int(f['where'].split()[1]) for f in stale})}")
        M.write(m, manifest_path)
        m = M.from_json(manifest_path.read_text())

    # 5. stills
    still_shots = [s for s in m.shots if s.kind != "video"]
    to_sweep = [s.index for s in still_shots if not s.candidates]
    if to_sweep:
        run_dir = out / (f"stills" if not st["still_runs"] else f"stills-{len(st['still_runs']) + 1}")
        summ = tools.still_sweep(manifest_path, to_sweep, stills_n, seed_stills, run_dir)
        st["still_runs"].append(str(run_dir)); save_state(out, st)
        if summ.get("no_survivors"):
            raise Stop(f"shots {summ['no_survivors']} have no surviving still: change candidates.seed_base_stills and resume")
        m = M.from_json(manifest_path.read_text())
    if mode == "assisted":
        for rd in st["still_runs"]:
            if (Path(rd) / "pick_form.md").exists():
                tools.still_apply_form(manifest_path, Path(rd))
        m = M.from_json(manifest_path.read_text())
        unpicked = [s.index for s in m.shots if s.kind != "video" and s.pick is None]
        if unpicked:
            st["stages"]["stills"] = "waiting"; save_state(out, st)
            forms = ", ".join(str(Path(rd) / "pick_form.md") for rd in st["still_runs"])
            raise Stop(f"WAITING for still picks on shots {unpicked}: fill {forms} then\n"
                       f"  python3 run_brief.py resume {brief_path} --out {out}", EXIT_WAITING)
    else:
        if any(s.kind != "video" and s.pick is None for s in m.shots):
            tools.still_provisional(manifest_path)
            m = M.from_json(manifest_path.read_text())
    done("stills")

    # 6. clips
    video_specs = [(i, s) for i, s in enumerate(b["shots"]) if s["kind"] == "video"]
    swept_any = False
    for i, spec in video_specs:
        shot = m.shots[i]
        if shot.candidates:
            continue
        if m.shots[spec["source_shot"]].asset == PLACEHOLDER:
            raise Stop(f"shot {i}'s source shot {spec['source_shot']} has no chosen still yet")
        tools.clip_sweep(manifest_path, i, spec["source_shot"], spec["motion"], clips_n, seed_clips, out / f"clips-shot{i:02d}")
        swept_any = True
        m = M.from_json(manifest_path.read_text())
    if swept_any:
        print(RESTART_REMINDER)
    if video_specs:
        if mode == "assisted":
            for i, _ in video_specs:
                rd = out / f"clips-shot{i:02d}"
                if (rd / "pick_form.md").exists() and m.shots[i].pick is None:
                    tools.still_apply_form(manifest_path, rd)
            m = M.from_json(manifest_path.read_text())
            unpicked = [i for i, _ in video_specs if m.shots[i].pick is None]
            if unpicked:
                st["stages"]["clips"] = "waiting"; save_state(out, st)
                forms = ", ".join(str(out / f"clips-shot{i:02d}" / "pick_form.md") for i in unpicked)
                raise Stop(f"WAITING for clip picks on shots {unpicked}: fill {forms} then\n"
                           f"  python3 run_brief.py resume {brief_path} --out {out}", EXIT_WAITING)
        else:
            for i, _ in video_specs:
                if m.shots[i].pick is None:
                    tools.clip_provisional(manifest_path, i)
            m = M.from_json(manifest_path.read_text())
    done("clips")

    # 7. render
    unpicked = [s.index for s in m.shots if s.asset == PLACEHOLDER]
    if unpicked:
        raise Stop(f"shots {unpicked} are still on the placeholder; pick them (forms / repick.py) and resume")
    assets = {str(s.index): s.asset for s in m.shots}
    assets["audio"] = m.audio
    changed = [i for i, a in assets.items() if st["last_render_assets"].get(i) != a]
    if st["stages"]["render"] == "done" and not changed:
        print("nothing to do: rendered and no picks changed since")
        return 0
    if st["last_render_assets"]:
        shots_changed = [i for i in changed if i != "audio"]
        print("re-rendering:" + (" audio changed;" if "audio" in changed else "")
              + (f" assets changed for shots {shots_changed}" if shots_changed else " no shot assets changed"))
    cut = out / f"{name}.mp4"
    tools.render(manifest_path, cut, out / "work")
    st["last_render_assets"] = assets
    done("render")
    print(f"-> {cut}" + (f"  (+ loop cut, see {cut.with_name(cut.stem + '_loop.mp4').name})" if m.loop else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["run", "resume"])
    ap.add_argument("brief")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["assisted", "provisional"], default="assisted")
    ap.add_argument("--server", default=ss.comfy_client.DEFAULT_SERVER)
    ap.add_argument("--accept-brief-change", action="store_true")
    ap.add_argument("--allow-low-confidence", action="store_true",
                    help=f"proceed even when more than {LOW_CONFIDENCE_MAX:.0%} of lyric lines were interpolated")
    args = ap.parse_args(argv)
    try:
        return run(Path(args.brief).resolve(), Path(args.out).resolve(), mode=args.mode,
                   tools=Tools(args.server), accept_brief_change=args.accept_brief_change,
                   allow_low_confidence=args.allow_low_confidence)
    except BriefError as e:
        print(f"brief invalid: {e}", file=sys.stderr)
        return 1
    except Stop as e:
        print(str(e), file=sys.stderr)
        return e.code
    except (M.ManifestError, cs.CullError, clc.ClipError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
