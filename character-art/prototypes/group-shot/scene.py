#!/usr/bin/env python3
"""The one scene every route is measured on.

Held fixed across all four routes so a difference in the output is a difference in the route.
Cast, tags and identity features come from `../../roster/cast.csv` unchanged -- they are WI 1599's
frozen subjects, carried through WI 1611, so an identity judgement here is comparable to the ones
already recorded rather than being about a fresh set of characters.

The target order is deliberately **not** the roster order (spike.md FC2). A route that reproduces
the order the characters are listed in has not been controlled; it has echoed an enumeration.
"""
from __future__ import annotations

from dataclasses import dataclass

# SDXL landscape bucket for generation; everything is scored at 2x this.
GEN_W, GEN_H = 1344, 768
SCORE_W, SCORE_H = GEN_W * 2, GEN_H * 2


@dataclass(frozen=True)
class Figure:
    cid: str
    display: str
    features: tuple[str, ...]   # the test oracle, fixed before any image exists
    tags: str                   # identity tags only -- framing is the scene's job, not the figure's
    x0: float                   # region, as a fraction of canvas width
    x1: float


# Left to right. Roster order is tiefling, dragonborn, halforc, human; this is not that.
CAST = (
    Figure("halforc", "Grum Ironjaw",
           ("tusk pair", "jaw mass", "green skin"),
           "1boy, half-orc, green skin, tusks, protruding lower canines, heavy brow, muscular, "
           "black braided hair, fur and leather armor",
           0.00, 0.28),
    Figure("tiefling", "Sera Ashfall",
           ("horn pair", "tail with spade tip", "red skin"),
           "1girl, tiefling, red skin, long curved horns, demon tail, pointed ears, yellow eyes, "
           "white hair, brown leather armor",
           0.25, 0.50),
    Figure("human", "Aldric Vane",
           ("face identity", "beard", "no non-human features"),
           "1boy, human, tan skin, short brown hair, short beard, brown leather armor",
           0.50, 0.75),
    Figure("dragonborn", "Vexaryn",
           ("snout", "scale texture", "no human nose"),
           "1other, dragonborn, draconic humanoid, dragon head, long snout, bronze scales, horns, "
           "frills, reptilian eyes, sharp teeth, steel plate armor",
           0.72, 1.00),
)

QUALITY = "masterpiece, best quality, very aesthetic, absurdres"

# The setting, shared by every route including the route 2 backdrop, so a composite is judged
# against the same lighting story a single pass was asked for.
SETTING = ("tavern interior, wooden beams, stone floor, warm lantern light, "
           "rim light from the left, fantasy adventurers, full body, standing")

NEG = ("bad quality, worst quality, worst detail, sketch, censored, blurry, lowres, "
       "jpeg artifacts, extra digits, fewer digits, bad hands, text, watermark, signature")

SEEDS = (5101, 5102, 5103)


def scene_prompt() -> str:
    """Route 1's prompt: every character described in one string, which is the only thing the tag
    lane can do unaided.

    This is where the 77-token CLIP budget bites. Four identity blocks plus quality plus setting is
    far past it, and ComfyUI chunks rather than truncates -- so the tokens are all present and none
    of them are reliably bound to a figure. That is a property of the route, not a flaw in how it
    is being run here, and it is the honest strongest form of route 1.
    """
    who = ", ".join(f.tags for f in CAST)
    return f"{QUALITY}, 4people, group of four, {SETTING}, {who}"


def region_prompt(f: Figure) -> str:
    """Route 4's per-region prompt. Each stays inside the token budget on its own."""
    return f"{QUALITY}, solo, {f.tags}, standing, full body"


def base_prompt() -> str:
    """Route 4's global conditioning: the scene without any character in it. Carries the lighting
    and setting that the regions must agree with."""
    return f"{QUALITY}, {SETTING}, group of four adventurers"


def backdrop_prompt() -> str:
    """Route 2's environment plate -- the same setting with nobody in it."""
    return (f"{QUALITY}, {SETTING}, empty tavern interior, no people, "
            "wooden tables, hearth, warm lantern light")


def target_order() -> tuple[str, ...]:
    return tuple(f.cid for f in CAST)
