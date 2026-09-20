#!/usr/bin/env python3
"""WI 1599 - regenerate dragonborn candidates without the muzzle-tack artifact.

"muzzle" in the first pass was read as harness rather than anatomy, putting a
gold strap across every snout. That ornament clutters the snout feature the
rubric scores, so it is prompted out and negated.
"""
import gen_portraits as g

PROMPT = (
    "1other, dragonborn, draconic humanoid, dragon head, reptile head, "
    "long snout, elongated jaw, bronze scales, scaled skin, horns, frills, "
    "reptilian eyes, sharp teeth, no human nose, muscular, steel plate armor, "
    "fantasy adventurer, " + g.COMMON
)
g.NEG = g.NEG + ", muzzle, harness, strap, bridle, mask, face mask, gag, headgear"
g.SUBJECTS = {"dragonborn2": PROMPT}
g.SEEDS = [404, 505, 606]
g.main()

