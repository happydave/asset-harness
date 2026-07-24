# Findings: ACE-Step 1.5 native lyric timing — real, but not reachable as a ComfyUI node

**Date:** 2026-07-23
**Track:** music-video (composite)
**Verdict:** partial — the model-native route **exists and is cross-attention-derived** (WI 989's
premise is now **Confirmed**), but a custom **ComfyUI node** is the wrong means to it, and the route
we actually have installed (`acestep_v1.5_xl_base_bf16`) is blocked on a missing alignment-layer
config. **Default route stays post-hoc** ([WI 1001](../../../../tickets/docs/pending/1001-ah-music-video-lyric-alignment-spike/workitem.md)).

## Goal

Answer [WI 1003](../../../../tickets/docs/pending/1003-ah-music-video-acestep-lrc-node-spike/workitem.md):
can ACE-Step 1.5's own cross-attention be read out **through a custom ComfyUI node** to produce
line-level lyric timings, and does that beat the post-hoc route (Demucs → WhisperX → reconcile) that
WI 1001 already adopted (16/16 lines high-confidence, 0.04 s chorus self-consistency, 39 s CPU)?

This is a **source-read spike**. The decisive evidence is in code, not in a generated artifact — so
no generation was run, no ComfyUI change was made, and no GPU time on the shared `ai2` box was spent.

## Tooling

- **Model:** ACE-Step 1.5 XL/4B (`acestep_v1.5_xl_base_bf16.safetensors`), installed on `ai2`.
- **Upstream source:** the standalone **ACE-Step 1.5** repository, checked out on `ai2` at
  `/opt/ACE-Step-1.5` (git `6d467e4`).
- **ComfyUI port source:** `/opt/comfyui/comfy/ldm/ace/{ace_step15,attention,lyric_encoder,model}.py`
  and `/opt/comfyui/comfy_extras/nodes_ace.py`.

No model artifact changed, so there is no licensing delta from WI 1001 — the lyrics/tags gate is the
same one already recorded, re-affirmed, not re-argued (per [`../license-lane.md`](../license-lane.md)).

## §A — The premise is Confirmed: native LRC timing exists and reads cross-attention

WI 989 §3a recorded this at **Supported** (from derived docs). It is now **Confirmed** against upstream
source. In `acestep/core/generation/handler/lyric_timestamp.py`, `LyricTimestampMixin.get_lyric_timestamp()`
docstring: *"Generate LRC timestamps by aligning decoder cross-attention to lyric tokens."* The mechanism:

1. **A separate, post-generation forward pass.** It does *not* observe attention during sampling.
   Given the finished latent `pred_latent`, it adds a small amount of noise at a near-clean timestep
   `t = 1 / inference_steps`, and runs **one** decoder forward:
   `self.model.decoder(..., output_attentions=True, custom_layers_config=..., enable_early_exit=True)`.
2. **Captured attention** is `[Layers, Heads, Tokens, Frames]`; `enable_early_exit` runs only up to the
   configured alignment layers.
3. **Lyric-slice recovery** (`lyric_alignment_common._extract_lyric_segment`): the lyric token range is
   found by tokenizing the header prefix `# Languages\n{lang}\n\n# Lyric\n` (→ `start_idx`) and locating
   `<|endoftext|>` id `151643` (→ `end_idx`). Upstream recovers the slice from **token structure**, not
   from the packed-context masks WI 1003's plan worried about.
4. **Alignment** (`acestep/core/scoring/dit_alignment.py`, `MusicStampsAligner`): bidirectional
   consensus denoising — `row = softmax(dim=-1)` (token→frame) × `col = softmax(dim=-2)` (frame→token),
   quantile row/col suppression, power sharpening, z-score, median filter — then **DTW** to get token
   timestamps, merged into sentence timestamps and LRC text.
5. **Frame→seconds** (`dit_alignment.py:260`): `seconds_per_frame = total_duration_seconds / n_frames`.
   **Correction to WI 989:** the output is **duration-scaled**, not a fixed 25 Hz map. 25 Hz is the
   internal latent rate; the emitted timing divides the *measured* duration by the *actual* frame count,
   which is more robust than a hardcoded rate.

**Two corrections to WI 989's wording** (both independently confirmed by a web read of the same upstream
files at `github.com/ace-step/ACE-Step-1.5`, which agreed with the on-box checkout on every point —
file names, the 2B config dict verbatim, and the `precomputed_lm_hints_25Hz`-is-an-input finding):

- It is **DTW over the (negated) attention matrix** (`dtw_cpu(-calc_matrix)`), not raw peak-picking.
- There is **no "merge heuristic for lines <2.0 s apart"** — lines are segmented on newlines, and each
  line's span is its first/last constituent token's time. The `2.0` WI 989 cited is the aligner's
  `violence_level` denoising coefficient, **not** a 2-second line-merge gap. (WI 989's
  `precomputed_lm_hints_25Hz`-adjacent "25 Hz" and the timestamp path are also unrelated: the former is
  an *input* LM-hint conditioning signal, the latter reads `output_attentions`.)

**Exposure.** It is a first-class, documented feature — the Gradio UI carries an "LRC" / auto-LRC
control (*"Automatically generates timestamped lyrics (LRC format)... karaoke-style"*) that calls
`dit_handler.get_lyric_timestamp(...)`; it has its own tests (`lyric_alignment_test.py`,
`session_artifacts_usage_test.py`). Not internal or experimental.

## §B — The ComfyUI port cannot host this. The subsystem was dropped, not merely un-wired.

WI 989 §3b said the feature is "not reachable from the ComfyUI nodes." That is **Confirmed and stronger
than stated**: ComfyUI's vendored port kept the *generation* path and dropped the entire *scoring/
alignment* subsystem. Grep of `/opt/comfyui/comfy/ldm/ace/` + `nodes_ace.py` for
`output_attentions | enable_early_exit | custom_layers_config | MusicStampsAligner | stamps_align |
get_lyric_timestamp | dit_alignment` → **zero matches.** Concretely:

- `AceStepAttention.forward` ends in `optimized_attention(...)` (SDPA/flash/xformers), which **returns
  no attention probabilities**. There is no `output_attentions` flag, no math-path fallback, no
  intermediate to capture.
- The vendored decoder `forward` signatures do not accept `output_attentions` / `enable_early_exit` /
  `custom_layers_config`.
- There is no `MusicStampsAligner`, no `_extract_lyric_segment`, no DTW — none of §A's steps 3–4.

So a ComfyUI custom node **cannot wire out an existing computation**. It would have to *reimplement the
whole subsystem*: monkey-patch the vendored attention to materialise weights on selected layers (a
second, slower math-path attention alongside the fast one, costing `[heads, frames, ctx]` memory per
captured layer), replicate the header-token slice extraction, and port the entire denoise+DTW aligner —
all pinned to ComfyUI internals that change without notice. That is a large, fragile maintenance
surface, and it is the failure mode WI 1003's plan named: **a route that silently degrades is worse
than one that fails loudly, because the output looks the same either way.**

## §C — The XL/4B checkpoint we have is itself blocked on a missing config

Even the *supported* upstream path would produce **wrong** timestamps on our checkpoint as installed.
`lyric_alignment_common._DEFAULT_LAYERS_CONFIG = {2:[6], 3:[10,11], 4:[3], 5:[8,9], 6:[8]}` is **2B
only**, and the upstream comment is explicit:

> XL (4B) models MUST provide `lyric_alignment_layers_config` in their config.json — this default will
> produce incorrect alignment for XL because XL has 32 layers / 32 heads vs 24 layers / 16 heads in 2B.

The installed `acestep_v1.5_xl_base_bf16.safetensors` carries **only `{format}` in its metadata**, and
there is **no accompanying `config.json`** on the box. So the required XL layer/head map is not present;
upstream would silently fall back to the 2B default it calls wrong. This **answers WI 989 Open Question
5** ("does the XL/4B checkpoint even support the feature usably?"): the *mechanism* is present, but the
*XL config* is not — so not usable as-installed without first obtaining or deriving the 32-layer/32-head
alignment config (or switching to a 2B checkpoint, for which the config ships).

*(Unresolved-but-not-load-bearing: the XL model's HF repo may publish a `config.json` with the XL
alignment config that we simply have not downloaded. That would unblock **route A**, not the node
verdict. Left at Supported pending a HF check.)*

## Verdict

**Do not build the ComfyUI custom node (route B).** It is dominated three ways:

1. **Wrong means.** The model-native timings are already exposed by a supported API in the standalone
   repo (`get_lyric_timestamp()`). WI 1003's own plan: *"the node is the preferred means, not the
   point."* The node would reimplement, against ComfyUI internals, a subsystem the port deliberately
   dropped — for data that a supported method already returns.
2. **Blocked anyway.** On the XL/4B checkpoint we have, native alignment needs a
   `lyric_alignment_layers_config` that is not present (§C). The node inherits this blocker.
3. **The baseline already wins.** Post-hoc (WI 1001) delivers 16/16 high-confidence at 39 s on CPU,
   model-independent, no ComfyUI change. A challenger is worth adopting only if it beats that on an axis
   that matters; the node beats it on **none** and loses on maintainability and setup cost.

**Default route: post-hoc (WI 1001), retained as primary and sole route for now.** Model-native timing
is real and desirable *in principle* (no ASR step; no melisma failure mode; timings from what the model
did). If it is ever wanted, the honest path is **route A — the standalone ACE-Step 1.5 repo's
`get_lyric_timestamp()`**, not a node, and only after (a) the XL alignment-layer config is obtained or a
2B checkpoint is adopted, and (b) it demonstrably beats post-hoc's 0.04 s chorus self-consistency on the
same song. That is a **future work item, not this one** — and it is route A, which WI 1003 explicitly
fenced out of scope.

**Head-to-head automated comparison (§C of the plan) was deliberately not run.** It requires generating
on the shared `ai2` box through the standalone repo's own environment (a WI-1002-class ROCm/shared-
service decision, owner-gated), and — decisively — the missing XL config means any native timestamps
today would be untrustworthy: the comparison would measure the config gap, not the route. Running it
would be measuring the wrong thing convincingly, which the spike exists to avoid.

## Repeatability

Entirely deterministic — every claim is a source read, reproducible by the greps and `sed` line ranges
cited above against `/opt/ACE-Step-1.5` (git `6d467e4`) and `/opt/comfyui/comfy/ldm/ace/` on `ai2`.

## Next

- **No node.** WI 1003 closes with a negative verdict on route B (a successful spike outcome).
- **If model-native timing is later wanted:** a *new* work item for **route A** — stand up the
  standalone repo on `ai2` (env + the shared-box decision), resolve the XL `lyric_alignment_layers_config`
  (download the XL model's `config.json` from HF, or derive the layers, or use a 2B checkpoint), and run
  the head-to-head against WI 1001's committed timeline on `clamor_hold_the_line_seed701.flac`.
- **WI 1004 (walking skeleton) is unaffected:** it uses the post-hoc timeline, which is done and works.
