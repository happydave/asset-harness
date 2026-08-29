#!/usr/bin/env python3
"""WI 1179 spike: VLM-as-judge for still selection, scored against ARCHIVED owner rankings.

Retrospective by construction — no generation, no owner time. Two corpora:

  A (primary, pre-registered)  WI 1037: shot4 + shot7, five Z-Image candidates each, with the owner's
                               blind FULL ranking, plus the off-brief sanity image ranked inside shot4.
  B (secondary, held out)      WI 1111 scienceranch imagery: six slots x three seeds, with the owner's
                               shipped PICK per slot. Top-1 only, different brief. Included because two
                               groups cannot support the word "sustained".

The judge is asked the owner's own task: given the brief, order these images best to worst. It sees the
group in one request, greedy-decoded. Controls, all pre-registered in spike.md: the same group is run
twice (determinism), once reversed (position bias), the off-brief image must land last (sanity floor),
and corpus B reports the "always answer first" rate (4/6 by construction) beside the result.

Stdlib + ffmpeg; talks to a llama.cpp server over its OpenAI-compatible endpoint.

    python3 vlm_judge.py --server http://ai2:8080 --corpus a --out vlm_a.json
"""
from __future__ import annotations

import argparse
import base64
import itertools
import json
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent
STILLS = PROTO / "outputs" / "spike1037" / "stills"
SR_IMAGERY = PROTO / "outputs" / "scienceranch-imagery"

STYLE = ("painterly tabletop RPG concept art, dramatic volumetric light, warm lantern glow against "
         "cool blue shadows, cinematic wide establishing shot, richly detailed, muted desaturated "
         "palette, moody atmospheric")

# --- corpus A: the pre-registered set ---------------------------------------------------------------
# Prompts are the ones the candidates were generated from (scoring/score.py, WI 1045).
A_PROMPTS = {
    "shot4": ("two survivors inside a dark ruined building, one holding up a burning red flare that "
              "casts dramatic light, a menacing shadow looming in a broken stairwell behind them, "
              "tense, " + STYLE),
    "shot7": ("dawn breaking over a ruined city as silhouetted survivors walk away toward a fortified "
              "colony gate glowing with warm safe light, hope and resolution, wide cinematic vista, "
              + STYLE),
}
# Owner's blind ranking, best -> worst, de-anonymised through ranking/_label_key.json.
A_OWNER = {
    "shot4": ["shot4_seed45.png", "shot4_seed42.png", "shot4_seed43.png",
              "shot4_seed41.png", "shot4_seed44.png"],
    "shot7": ["shot7_seed44.png", "shot7_seed43.png", "shot7_seed42.png",
              "shot7_seed41.png", "shot7_seed45.png"],
}
SANITY = "sanity_offbrief_seed41.png"      # ranked inside shot4's group; must come last

USE_CASE = ("a shot in a lyric-driven music video for a post-apocalyptic zombie-survival game, "
            "shown full-screen for a few seconds behind sung lyrics")


def presentation_order(names: list[str], group: str) -> list[str]:
    """A fixed, group-seeded shuffle — NOT the owner's order and NOT seed order.

    Presenting candidates in the owner's ranked order would hand a position-biased judge a free win:
    "always answer 1,2,3,4,5" would then score a perfect rho. Seed order is no better on corpus B, where
    the owner picked the first-listed seed in four of six slots. The shuffle is deterministic (seeded by
    the group name) so runs are reproducible, and the reversed control re-presents the same images in
    the opposite order.

    The salt is chosen so that the arrangement is adversarial rather than merely random: under it the
    owner's favourite is never in position 1 — not in either corpus-A group, and in none of corpus B's
    six slots. A judge that answers by position therefore scores zero top-1, not a free win. (Chosen
    before any judging, on the arrangement alone; the first salt tried put the owner's top first in both
    A groups, which is exactly the confound the shuffle exists to remove.)
    """
    rng = random.Random(f"wi1179-order:{group}")
    shuffled = list(names)
    rng.shuffle(shuffled)
    return shuffled


def corpus_a(with_sanity: bool = False, order: str = "shuffled") -> list[dict]:
    """`order="owner"` presents candidates in the owner's own ranked order — the position-bias control.

    It is the arrangement the first draft of this harness used by accident, and it flattered the judge
    badly: a judge that answers "1,2,3,4,5" scores a perfect rho under it. Kept as an explicit control
    so the effect is measured rather than described.
    """
    groups = []
    for name, prompt in A_PROMPTS.items():
        files = list(A_OWNER[name])
        if with_sanity and name == "shot4":
            files = files + [SANITY]
        files = files if order == "owner" else presentation_order(files, name)
        groups.append({"group": name, "brief": prompt, "use_case": USE_CASE,
                       "images": [str(STILLS / f) for f in files], "owner_order": A_OWNER[name]})
    return groups


# --- corpus B: the held-out extension ---------------------------------------------------------------
# Prompts and picks come from the WI 1111 manifest (tickets/docs/pending/1111-.../manifest.md).
B_BRIEF_TAIL = ("cinematic concept art, warm lantern amber light held against deep blue-black dusk, "
                "volumetric haze, calm curious methodical mood, richly detailed, moody atmospheric")
B_SLOTS = {
    "hero": (202, "a very wide establishing shot of a small ranch homestead at dusk on a vast open "
                  "plain, warm lit windows and a single porch lantern holding light against the deep "
                  "blue-black land and sky, first stars, distant low hills, "),
    "lab": (101, "a night workshop interior, a wheeled garden robot chassis partly assembled on a "
                 "workbench under a single warm work lamp, neat tools and an oscilloscope glow, deep "
                 "blue shadow beyond the lamplight, "),
    "ranch": (303, "a homestead pantry at dusk, wooden shelves of glass jars of preserved and "
                   "freeze-dried food glowing warm in lantern light, braided herbs hanging, deep blue "
                   "evening light through a small window, "),
    "ai": (101, None),
    "readiness": (101, None),
    "games": (101, None),
}
B_USE_CASE = ("a section cover image on a personal website with a dark 'after dark' theme, seen at the "
              "top of that section")


def corpus_b(prompts: dict) -> list[dict]:
    groups = []
    for slot, (pick, _) in B_SLOTS.items():
        files = [SR_IMAGERY / n
                 for n in presentation_order([f"{slot}_s{s}.png" for s in (101, 202, 303)], slot)]
        missing = [f for f in files if not f.is_file()]
        if missing:
            raise SystemExit(f"corpus B: missing {missing}")
        groups.append({"group": slot, "brief": prompts[slot], "use_case": B_USE_CASE,
                       "images": [str(p) for p in files],
                       "owner_pick": f"{slot}_s{pick}.png"})
    return groups


# --- the judge --------------------------------------------------------------------------------------
MAX_EDGE = 1280          # corpus B is 1920x1088; corpus A is already 1280x720 and passes through


def encode_image(path: Path, max_edge: int = MAX_EDGE) -> str:
    """PNG bytes as a data URL, downscaled only if the long edge exceeds `max_edge`."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
         "-vf", f"scale='min({max_edge},iw)':-2", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True).stdout
    return "data:image/png;base64," + base64.b64encode(out).decode()


PAIRWISE_TEMPLATE = """You are helping choose which generated image to use for {use_case}.

Both images were generated from this brief:
"{brief}"

Compare the two the way an art director would: how well each serves the brief, how well it reads at a
glance, composition and lighting, and whether anything in it is broken or distracting (malformed
anatomy, garbled text, incoherent objects).

Reply with exactly two lines and nothing else:
REASON: <one sentence on what separates them>
WINNER: <1 or 2>"""

POINTWISE_TEMPLATE = """You are helping choose which generated image to use for {use_case}.

The image was generated from this brief:
"{brief}"

Judge THIS ONE image the way an art director would: how well it serves the brief, how well it reads at
a glance, its composition and lighting, and whether anything in it is broken or distracting (malformed
anatomy, garbled text, incoherent objects).

Reply with exactly two lines and nothing else:
REASON: <one sentence>
SCORE: <an integer from 0 to 100, where 100 is an image you would ship unchanged>"""

PROMPT_TEMPLATE = """You are helping choose which generated image to use for {use_case}.

The image was generated from this brief:
"{brief}"

You are shown {n} candidates, labelled 1 to {n} in the order presented. Judge them the way an art
director would: how well each one serves the brief, how well it reads at a glance, its composition and
lighting, and whether anything in it is broken or distracting (malformed anatomy, garbled text,
incoherent objects).

Reply with exactly two lines and nothing else:
REASON: <one sentence on what separates your first choice from your last>
RANKING: <the labels best to worst, comma-separated>"""


def ask(server: str, group: dict, order: list[int], seed: int, timeout: int = 900) -> dict:
    """One judging request. `order` is the presentation order (indices into group['images'])."""
    images = [Path(group["images"][i]) for i in order]
    content = [{"type": "text", "text": PROMPT_TEMPLATE.format(
        use_case=group["use_case"], brief=group["brief"], n=len(images))}]
    for n, p in enumerate(images, 1):
        content.append({"type": "text", "text": f"Candidate {n}:"})
        content.append({"type": "image_url", "image_url": {"url": encode_image(p)}})
    body = {"model": "vlm-judge", "messages": [{"role": "user", "content": content}],
            "temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": seed, "max_tokens": 300}
    req = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    text = resp["choices"][0]["message"]["content"]
    ranked = parse_ranking(text, len(images))
    return {"raw": text.strip(),
            "presented": [Path(p).name for p in images],
            "ranking": [images[i - 1].name for i in ranked] if ranked else None}


def ask_pointwise(server: str, group: dict, index: int, seed: int, timeout: int = 900) -> dict:
    """Score ONE candidate on its own. No other candidate is in the request, so position cannot bias it.

    This is the protocol the listwise run forced: a judge that answers by presentation order has no
    position to answer by when it sees one image at a time. What it cannot do is compare — the ranking
    is assembled afterwards from independent scores, so ties are real and are reported as ties.
    """
    path = Path(group["images"][index])
    content = [{"type": "text", "text": POINTWISE_TEMPLATE.format(
        use_case=group["use_case"], brief=group["brief"])},
        {"type": "image_url", "image_url": {"url": encode_image(path)}}]
    body = {"model": "vlm-judge", "messages": [{"role": "user", "content": content}],
            "temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": seed, "max_tokens": 200}
    req = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    text = resp["choices"][0]["message"]["content"]
    m = re.search(r"SCORE\s*:\s*(\d+)", text, re.I)
    return {"image": path.name, "score": int(m.group(1)) if m else None, "raw": text.strip()}


def ask_pairwise(server: str, group: dict, i: int, j: int, seed: int, timeout: int = 900) -> dict:
    """Ask which of two candidates is better. Two images per request, so the comparison is explicit.

    Every pair is asked in BOTH orders. A judge reading content gives the same winner either way; one
    reading position flips. The flip rate is therefore a direct measurement of position bias rather
    than a yes/no control.
    """
    a, b = Path(group["images"][i]), Path(group["images"][j])
    content = [{"type": "text", "text": PAIRWISE_TEMPLATE.format(
        use_case=group["use_case"], brief=group["brief"])}]
    for n, p in ((1, a), (2, b)):
        content.append({"type": "text", "text": f"Image {n}:"})
        content.append({"type": "image_url", "image_url": {"url": encode_image(p)}})
    body = {"model": "vlm-judge", "messages": [{"role": "user", "content": content}],
            "temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": seed, "max_tokens": 200}
    req = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    text = resp["choices"][0]["message"]["content"]
    m = re.search(r"WINNER\s*:\s*([12])", text, re.I)
    win = None if not m else (a.name if m.group(1) == "1" else b.name)
    return {"left": a.name, "right": b.name, "winner": win, "raw": text.strip()}


def pairwise_group(server: str, group: dict, seed: int) -> dict:
    """Every unordered pair, both orders. Returns win counts, the ranking they imply, and the flip rate."""
    n = len(group["images"])
    names = [Path(p).name for p in group["images"]]
    wins = {x: 0 for x in names}
    matches, flips, pairs = [], 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            fwd = ask_pairwise(server, group, i, j, seed)
            rev = ask_pairwise(server, group, j, i, seed)
            matches += [fwd, rev]
            pairs += 1
            if fwd["winner"] and rev["winner"] and fwd["winner"] == rev["winner"]:
                wins[fwd["winner"]] += 1          # consistent across order: a real win
            else:
                flips += 1                        # order decided it: half a point each, no signal
                for x in (names[i], names[j]):
                    wins[x] += 0.5
    ranking = sorted(names, key=lambda x: (-wins[x], names.index(x)))
    return {"kind": "pairwise", "wins": wins, "ranking": ranking, "pairs": pairs,
            "order_flips": flips, "flip_rate": round(flips / pairs, 3) if pairs else None,
            "matches": matches, "presented": names}


def parse_ranking(text: str, n: int) -> list[int] | None:
    """Pull `RANKING: 3,1,2` out of the reply. Returns 1-based labels, or None if unusable."""
    m = re.search(r"RANKING\s*:\s*([0-9,\s]+)", text, re.I)
    if not m:
        return None
    labels = [int(x) for x in re.findall(r"\d+", m.group(1))]
    if sorted(labels) != list(range(1, n + 1)):
        return None
    return labels


# --- metrics ----------------------------------------------------------------------------------------
def spearman(order_a: list, order_b: list) -> float:
    """rho between two orderings of the same items (best-first). Same formula as compare_rankings.py."""
    ra = {x: i + 1 for i, x in enumerate(order_a)}
    rb = {x: i + 1 for i, x in enumerate(order_b)}
    n = len(order_a)
    d2 = sum((ra[x] - rb[x]) ** 2 for x in order_a)
    return 1 - (6 * d2) / (n * (n * n - 1))


def permutation_p(rho: float, n: int) -> float:
    """P(rho_random >= observed) over all n! orderings — what 'clearly above +0.30' has to beat."""
    base = list(range(n))
    hits = 0
    perms = list(itertools.permutations(base))
    for p in perms:
        if spearman(base, list(p)) >= rho - 1e-12:
            hits += 1
    return hits / len(perms)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="http://ai2:8080")
    ap.add_argument("--corpus", choices=["a", "b"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sanity", action="store_true", help="corpus A: add the off-brief image to shot4")
    ap.add_argument("--repeat", type=int, default=2, help="runs per group for the determinism control")
    ap.add_argument("--seed", type=int, default=1179)
    ap.add_argument("--order", choices=["shuffled", "owner"], default="shuffled",
                    help="corpus A presentation order; 'owner' is the position-bias control")
    ap.add_argument("--mode", choices=["listwise", "pointwise", "pairwise"], default="listwise",
                    help="listwise = rank the group in one request (the owner's task, but exposed to "
                         "position bias); pointwise = score each candidate alone, then rank by "
                         "score; pairwise = every pair in both orders, ranked by consistent wins")
    ap.add_argument("--b-prompts", type=Path, default=HERE / "corpus_b_prompts.json")
    a = ap.parse_args()

    groups = corpus_a(a.sanity, a.order) if a.corpus == "a" else corpus_b(json.loads(a.b_prompts.read_text()))
    results = []
    if a.mode == "pairwise":
        for g in groups:
            runs = [pairwise_group(a.server, g, a.seed) for _ in range(a.repeat)]
            for r in runs:
                print(f"[{g['group']}] pairwise: {[x.split('_')[-1][:-4] for x in r['ranking']]}  "
                      f"flips {r['order_flips']}/{r['pairs']}", flush=True)
            results.append({**{k: v for k, v in g.items() if k != "images"},
                            "images": [Path(p).name for p in g["images"]], "runs": runs})
        a.out.write_text(json.dumps({"server": a.server, "corpus": a.corpus, "mode": a.mode,
                                     "seed": a.seed, "groups": results}, indent=2) + "\n")
        print(f"-> {a.out}")
        return 0
    if a.mode == "pointwise":
        for g in groups:
            runs = []
            for r in range(a.repeat):
                scored = [ask_pointwise(a.server, g, i, a.seed) for i in range(len(g["images"]))]
                ranking = [x["image"] for x in sorted(scored, key=lambda x: -(x["score"] or -1))]
                ties = len(scored) - len({x["score"] for x in scored})
                runs.append({"kind": "forward", "run": r, "scores": scored,
                             "ranking": ranking, "ties": ties,
                             "presented": [x["image"] for x in scored]})
                print(f"[{g['group']}] pointwise {r}: "
                      f"{[(x['image'].split('_')[-1][:-4], x['score']) for x in scored]}", flush=True)
            results.append({**{k: v for k, v in g.items() if k != "images"},
                            "images": [Path(p).name for p in g["images"]], "runs": runs})
        a.out.write_text(json.dumps({"server": a.server, "corpus": a.corpus, "mode": a.mode,
                                     "seed": a.seed, "groups": results}, indent=2) + "\n")
        print(f"-> {a.out}")
        return 0
    for g in groups:
        n = len(g["images"])
        runs = []
        for r in range(a.repeat):                       # identical input, identical seed
            runs.append({"kind": "forward", "run": r, **ask(a.server, g, list(range(n)), a.seed)})
            print(f"[{g['group']}] forward {r}: {runs[-1]['ranking']}", flush=True)
        rev = ask(a.server, g, list(reversed(range(n))), a.seed)
        rev["kind"] = "reversed"
        runs.append(rev)
        print(f"[{g['group']}] reversed: {rev['ranking']}", flush=True)
        results.append({**{k: v for k, v in g.items() if k != "images"},
                        "images": [Path(p).name for p in g["images"]], "runs": runs})

    a.out.write_text(json.dumps({"server": a.server, "corpus": a.corpus, "seed": a.seed,
                                 "groups": results}, indent=2) + "\n")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
