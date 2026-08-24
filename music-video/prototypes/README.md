# music-video prototypes — ComfyUI client conventions

Throwaway prototypes driving ComfyUI on `ai2`. They all share one hard-won rule about **waiting on
jobs** — captured here so it stops being re-learned (it cost WI 1013/1015/1018 real time, incl. a lost
overnight batch).

## The waiting rule (WI 1020)

**Wait on the server's terminal job state, never a wall-clock cap and never a `pgrep` on a client
process.**

- A job **absent from `/history`** is *still pending or running* → keep waiting. It is NOT a timeout.
  (The old `while time.time()-t0 < timeout` discarded finished clips whose run outlasted a guessed
  timeout — a cold no-LoRA 720p clip is ~108 min and blew a 100-min cap.)
- The optional `--timeout` on the clients is a **backstop**, not a cap: default is to wait
  indefinitely, and if a backstop is set and exceeded, the client exits **with the `prompt_id` and the
  recovery command**, never by throwing the result away.
- A job is only "failed" if the **server** says `error`, or it **vanished** (absent from both
  `/history` and `/queue` past a short grace — a submit failure, the one case indefinite waiting must
  not apply to).
- Batches sequence on **job/artifact state**, never `while pgrep client.py` (that wedged the WI 1018
  batch for ~6 h when one client timed out).

All of this lives in **`comfy_client.py`** — use it, don't hand-roll a wait loop:

```python
import comfy_client
paths = comfy_client.run_job(server, graph, out_stem, kinds=("videos",), backstop=None, label="shot1")
```

## Files

- **`comfy_client.py`** — shared helpers: `queue`, `wait_for_history` (the rule above),
  `download_outputs`, `run_job` (queue→wait→download), `fetch_from_history`.
- **`fetch_from_history.py`** — recover a finished prompt's outputs after the fact
  (`--pid <id>` or `--filename <substr>`), for when a client exited before downloading.
- **`run_batch.py`** — run a list of clip specs sequentially, each keyed on job state; one clip's
  failure is caught and the batch continues.
- **`generate_clip.py`** — Wan2.2 i2v; use **`--fp16`** (two-stage, the delivered recipe).
  **`generate_still.py`** — opaque Z-Image text-to-image. **`generate_song.py`** — ACE-Step 1.5
  song-with-lyrics. All three use `comfy_client`.
- **`generate_clip_single.py`** — an **abandoned** single-expert Wan variant, kept as a record of the
  experiment. Do not use it for delivery; see its header and
  [findings](../findings/2026-08-24-production-sessions.md).
- **`timeline.py`** — the lyric timeline (JSON + LRC); every alignment route emits it.
- **`manifest.py`** — the shot-list manifest schema (timeline → shots); the track's durable artifact.
  **`test_manifest.py`** — 17 checks (`python3 test_manifest.py`).
- **`render.py`** — the pure renderer: manifest + assets → lobby-loop mp4 (workstation ffmpeg).
- **`build_lobby.py`** — the WI 1004 skeleton driver (authors the manifest, gens assets, renders).
- **`interpolate.py`** — workstation ffmpeg `minterpolate` fps raise (WI 1019 smoothness fix).

## Licence

Prompt hygiene per [`../license-lane.md`](../license-lane.md) applies to every generator here.
