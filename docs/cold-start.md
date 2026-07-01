# Cold Start

Zero-to-first-asset for a newcomer (or a returning maintainer with no context in
their head). Read this once, then live in the per-track docs.

## What you're looking at

Asset Harness is a set of **repeatable pipelines that turn prompts/specs into
game-ready assets**. It is not a game and it is not an art library — it's the
machinery that produces assets, plus the notes proving how each one was made.

The mental model, applied per asset class ("track"):

> **discovery** (what tools/models exist, do they run, what are their licenses)
> → **prototypes** (try them, capture outputs + provenance)
> → **harness** (a documented, repeatable script/procedure).

Outputs are **engine-agnostic**. A consuming game (Phaser/TS, Bevy/Rust,
Ebitengine/Go) imports them through a thin, per-engine step that lives in *that
game's* repo — not here.

## The one thing that surprises people

**The Python scripts in this repo are thin HTTP clients. They do no GPU work
themselves.** A track's `run_*.py` builds a [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
API graph, uploads any inputs, queues the job on a **ComfyUI server**, polls, and
downloads the result. All the model inference happens on that server.

So "getting set up" is really two things: a trivial Python client environment
here, and a **working ComfyUI server** (local or on another box) with the right
model weights installed. The weights are deliberately *not* in this repo
(`.gitignore` blocks `*.safetensors`, `*.ckpt`, `*.gguf`, …).

## Prerequisites

1. **Python 3** with a virtualenv. The generation scripts are stdlib + `requests`;
   some post-processing pulls in a little more. Per track:
   ```
   python3 -m venv .venv && . .venv/bin/activate
   pip install requests
   ```
2. **A reachable ComfyUI server** with the model artifacts a track needs already
   installed. Each track's [`discover.md`](../2d/discover.md) lists the exact
   artifact names (checkpoints, ControlNets, VAE) **and a license matrix** — read
   it before running and install those into your ComfyUI. Scripts default to
   `--server http://ai2:8188`; override it with your own host.
3. **ffmpeg** — for the `audio` track and any loop/normalize post-processing.
4. **Blender** — for the `3d-static-props` and `mechanical-kit` tracks (mesh
   cleanup, decimation, the parametric kit). Not needed for `2d`/`audio`.

### Hardware reality

The scripts run anywhere — the GPU demand is on the ComfyUI server, not the
client. Generation is developed against an **NVIDIA** workstation (RTX 5070) as
the reliable path; **AMD/ROCm** hosts (gfx1151 Strix Halo, gfx1201 R9700) are
used and their **failures are recorded as data, not hidden**. Don't expect AMD to
be turnkey; expect the findings to tell you where it broke.

## Walkthrough: your first asset (2d track)

The `2d` track is the most mature (🟢) and has the fastest feedback loop — start
here. It generates a top-down game sprite on a clean-license stack (Z-Image Turbo
+ Fun ControlNet + BiRefNet matte), all Apache/MIT.

```
cd 2d/prototypes
python run_zimage_controlnet.py \
  --server http://<your-comfyui-host>:8188 \
  --subject "a heavy cargo hauler with side pods and three engine nozzles" \
  --name hauler \
  --out outputs
```

What happens: the script Canny-edges a control image, drives Z-Image Turbo through
ComfyUI, mattes the background to clean alpha, and downloads three files to
`outputs/` (git-ignored): the **RGBA sprite**, the opaque render, and the Canny
map. A shared `STYLE` string is prepended to every subject so a whole fleet stays
visually coherent — that's the track's answer to style drift.

Pack sprites into an engine-ready atlas with the sibling script:

```
python build_atlas.py            # PNG + JSON atlas for Phaser/Ebitengine
```

Then, the step that makes it a *harness* and not a one-off:

**Record provenance.** Copy [`_template/findings.md`](../_template/findings.md) into
`2d/findings/<date>-<slug>.md` and fill it in — model/workflow/version,
prompt/seed/params, the **hardware it ran on**, the license chain, and a
`works / partial / fails` verdict. An asset without a findings entry is not done.

## Conventions you must honor

These are the rules that keep the repo trustworthy — see the
[README Conventions](../README.md#conventions) for the canonical wording:

- **Every prototype records provenance** in a `findings.md`. AMD failures included.
- **Every generation records its license chain.** The output's effective license is
  the *most restrictive link* across the base model and every LoRA/ControlNet. This
  gates whether an asset can ever go into a "clean", commercially redistributable
  pack.
- **Local-first.** Try ComfyUI locally before a hosted API; if you reach for a
  hosted service, note why local fell short.
- **Commit samples, not bulk.** Large outputs and weights are git-ignored; commit
  *representative* samples explicitly with `git add -f`, plus the findings that
  reproduce them.

## Where to go next

- The [tracks table](../README.md#tracks--status) — current status of every track.
- Each track's `README.md` (purpose + status), `discover.md` (**read first** —
  models, license matrix, what runs), `findings/` (worked examples), and
  `prototypes/` (the scripts).
- The [`_template/findings.md`](../_template/findings.md) — the shape every
  experiment gets written up in.
