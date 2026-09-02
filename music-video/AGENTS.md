# music-video — operator card

For an agent **operating** this pipeline: making a video from a brief. Read this, the model skill for
each step you touch, and nothing else unless stuck. **Operating the pipeline is not a code change** —
the workflow framework governs *developing* the pipeline, not running it (owner policy, 2026-09-01).

Generation runs on `ai2` (ComfyUI over HTTP). Alignment, scoring and assembly run on the workstation.
All commands below run from `prototypes/`.

## Make a video

1. **Preflight** — `python3 preflight.py`. Fix what it names before generating anything.
2. **Song** — `python3 generate_song.py --seeds 701,702,703` → three FLAC candidates. Lyrics and tags
   are the `SONG` block in the script today; edit them per `../skills/prompting-ace-step/SKILL.md`.
   The best candidate is the one the owner (or Audiobox CE, once WI 1176 lands) picks.
3. **Timeline** — `.venv/bin/python align_posthoc.py --audio <song>.flac --lyrics <sheet>.txt`. The
   sheet is the lyrics text with its `[verse]`/`[chorus]` tags. Fallback: `python3 tap_align.py`.
4. **Stills** — one `python3 generate_still.py --prompt "<scene>" --out <stem>` per shot; seconds each,
   so sweep seeds. Read `../skills/prompting-z-image/SKILL.md` first. The owner picks.
5. **Clips** — one or two hero shots only: `python3 generate_clip.py --image <still>.png
   --prompt "<motion>" --out <stem>`. Defaults are the recipe. Read
   `../skills/prompting-wan-i2v/SKILL.md` first.
6. **Manifest** — shots of `{lines, t_start, t_end, kind, prompt, asset, kb}` partitioning the song;
   `manifest.py` validates. `build_lobby.py` is the worked example until the brief-file driver
   (WI 1180) lands.
7. **Render** — `python3 render.py <manifest>.json --out <cut>.mp4`. A `loop` block in the manifest
   also emits the seamless loop cut.
8. **Record** — a findings entry per `../_template/findings.md`, including the license-lane check
   table.

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
