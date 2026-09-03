# music-video — operator card

For an agent **operating** this pipeline: making a video from a brief. Read this, the model skill for
each step you touch, and nothing else unless stuck. **Operating the pipeline is not a code change** —
the workflow framework governs *developing* the pipeline, not running it (owner policy, 2026-09-01).

Generation runs on `ai2` (ComfyUI over HTTP). Alignment, scoring and assembly run on the workstation.
All commands below run from `prototypes/`.

## Make a video

1. **Write the brief.** Copy `prototypes/inputs/clamor_hold_the_line.brief.json` and edit it: the
   song (name, seconds, bpm, key, tags, original lyrics with `[verse]`/`[chorus]` tags), a style
   string, one entry per shot (how many lyric lines it covers, `still`/`kenburns`/`video`, its image
   prompt or, for a video shot, a motion prompt and a non-adjacent `source_shot`), an optional loop
   block. `prototypes/brief.schema.json` is the contract. Read the model skill for the prompts you
   write: `../skills/prompting-ace-step/SKILL.md`, `prompting-z-image`, `prompting-wan-i2v`.
2. **Run it.** From `prototypes/`:
   `python3 run_brief.py run <brief>.json --out outputs/runs/<name> --mode provisional`
   runs preflight, the song stage (three seeds, truncation veto, Audiobox pick), alignment, the
   still sweep, the clip sweep and the render, drafting every pick and labelling it
   `machine-provisional`. Without `--mode provisional` it is **assisted**: it stops (exit 3) at each
   pick point, prints the form to fill, and `python3 run_brief.py resume <brief>.json --out <dir>`
   continues. `run.json` in the output folder says where a run stands.
3. **Change a pick.** `python3 repick.py pick <manifest> --shot N --to <asset> --by owner --reason "…"`
   (or `--song`) then `resume`: a song re-pick re-derives the timeline; a still re-pick re-renders.
4. **Record** a findings entry per `../_template/findings.md`, including the license-lane check table.

The stage tools also run on their own (`select_song.py`, `cull_stills.py`, `clip_candidates.py`,
`render.py`); the track README describes each.

## Rules

- **Prompt hygiene:** no franchise, character, living-artist or named-song references
  (`license-lane.md`). Vocals are for standalone media only, never for in-game audio.
- **Wan eats opaque RGB stills only.** Never place a clip next to its own source still in the cut.
- **Motion is an accent.** Most shots are Ken Burns stills.
- **Wait on job state, never a wall clock.** Use `comfy_client.run_job`; recover a lost download with
  `fetch_from_history.py --pid <id>`. A job absent from `/history` is still running.
- **After a Wan job, restart ComfyUI** before batching ACE-Step or Z-Image:
  `ssh ai2 systemctl restart comfyui.service`. A restart is fine; changing the service config is not.

## Never

- Use LTX, HunyuanVideo or Stable Video Diffusion. Wan2.2 is the only sanctioned video model.
- Pick stills or clips by machine score. Scorers gate; the owner selects.
- Hand-roll a wait loop, edit `ai2`'s service config, or install models on `ai2`.

## When stuck

- A clip past 5 min or stills crawling: restart ComfyUI (Rules). Two distinct slowdowns are described
  in `findings/2026-08-24-production-sessions.md`.
- Anything else: the track `README.md`, then `findings/`. History lives there, not here.
