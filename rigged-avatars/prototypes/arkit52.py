"""Canonical ARKit-52 clip contract for the rigged-avatars track (WI 1362, ladder step 6).

This module is the **single owner** of the 52 ARKit blendshape names and the VRM preset composition
table. Generators, validators and the downstream contracts sidecar all import from here; nothing
re-declares the list. A single character of casing drift is a silent runtime failure — Warudo binds
VRM 1.0 partly by raw blendshape name and VRM 0.x tools bind by clip name — so the list has one home
and it is deliberately not a generator.

Pure Python: no `bpy`. It imports under a plain `python3` so a non-Blender checker can use it.

Naming: these are Apple's public `ARFaceAnchor.BlendShapeLocation` identifiers, used as an interop
vocabulary. Google ships the identical 52 names as MediaPipe FaceLandmarker output under Apache-2.0.
Naming our own original shape keys after them involves none of Apple's code, data or geometry.
Describe the result as "ARKit-compatible" / "Perfect Sync", never as "ARKit(R)".
"""

# The 52, in ARKit's own alphabetical order, exact camelCase.
ARKIT_52 = (
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft",
    "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
    "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "noseSneerLeft", "noseSneerRight", "tongueOut",
)

# The 18 VRM 1.0 preset expression slots, as the saturday06 add-on v4.4.0 exposes them (read from a
# live introspection probe on ai2, 2026-09-07 — not from memory).
VRM1_PRESETS = (
    "aa", "ee", "ih", "oh", "ou",
    "angry", "happy", "relaxed", "sad", "surprised",
    "blink", "blink_left", "blink_right",
    "look_down", "look_left", "look_right", "look_up",
    "neutral",
)

# ---------------------------------------------------------------------------
# The stylized head archetype's authored set (WI 1362).
#
# The real-vs-stub split is a property of the ARCHETYPE, not of the project: the realistic archetype
# (WI 930) revisits the soft-tissue shapes stubbed here. The 8 eyeLook* shapes are stubs because gaze
# is bone-driven, which is the discovery's stated preference order, not a shortcut.
# ---------------------------------------------------------------------------

STYLIZED_V1_AUTHORED = (
    # --- WI 1362: the core that composes the 13 morph-driven presets -------------------------------
    "eyeBlinkLeft", "eyeBlinkRight",
    "eyeWideLeft", "eyeWideRight",
    "eyeSquintLeft", "eyeSquintRight",
    "browInnerUp", "browDownLeft", "browDownRight",
    "jawOpen",
    "mouthSmileLeft", "mouthSmileRight",
    "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthPucker",
    # --- WI 1363: the tranche. Outer brows FIRST, on live-tracker evidence rather than the ladder's
    # ordering: driving the WI 1362 avatar from a webcam put browOuterUp* and mouthStretchLeft in the
    # top-scoring blendshapes repeatedly, while the brows visibly failed to move.
    "browOuterUpLeft", "browOuterUpRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthStretchLeft", "mouthStretchRight",
    "mouthLeft", "mouthRight", "mouthClose",
    "jawLeft", "jawRight",
)

# Why each unauthored clip is a stub. Every one of the 52 is either authored or has a reason here.
STUB_REASONS = {
    "gaze-is-bone-driven": (
        "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
        "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    ),
    "no-visual-referent-on-a-stylized-face": (
        "cheekSquintLeft", "cheekSquintRight",
        "mouthDimpleLeft", "mouthDimpleRight", "mouthPressLeft", "mouthPressRight",
        "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
        "noseSneerLeft", "noseSneerRight",
    ),
    "not-webcam-driveable": ("cheekPuff", "jawForward", "tongueOut"),
}

# VRM 1.0 preset -> [(authored ARKit shape, weight)]. Fractional weights are the point: a viseme is a
# partial jaw plus a partial mouth shape, and hard-coding weight 1.0 (as the exporter did before
# WI 1362) cannot express one.
#
# NOT composed, deliberately:
#   neutral                                  - empty by definition
#   look_up / look_down / look_left / look_right - gaze is bone-driven (look_at.type = 'bone'), so an
#                                              empty look_* preset is correct, not a gap.
PRESET_COMPOSITION = {
    "blink":       [("eyeBlinkLeft", 1.0), ("eyeBlinkRight", 1.0)],
    "blink_left":  [("eyeBlinkLeft", 1.0)],
    "blink_right": [("eyeBlinkRight", 1.0)],

    "aa": [("jawOpen", 1.00)],
    "ih": [("jawOpen", 0.30), ("mouthSmileLeft", 0.40), ("mouthSmileRight", 0.40)],
    "ee": [("jawOpen", 0.15), ("mouthSmileLeft", 0.70), ("mouthSmileRight", 0.70)],
    "ou": [("jawOpen", 0.25), ("mouthPucker", 1.00)],
    "oh": [("jawOpen", 0.60), ("mouthFunnel", 1.00)],

    "happy":     [("mouthSmileLeft", 1.00), ("mouthSmileRight", 1.00),
                  ("eyeSquintLeft", 0.35), ("eyeSquintRight", 0.35)],
    "angry":     [("browDownLeft", 1.00), ("browDownRight", 1.00),
                  ("mouthFrownLeft", 0.45), ("mouthFrownRight", 0.45)],
    "sad":       [("browInnerUp", 1.00), ("mouthFrownLeft", 0.80), ("mouthFrownRight", 0.80)],
    "relaxed":   [("mouthSmileLeft", 0.45), ("mouthSmileRight", 0.45),
                  ("eyeSquintLeft", 0.55), ("eyeSquintRight", 0.55)],
    "surprised": [("eyeWideLeft", 1.00), ("eyeWideRight", 1.00),
                  ("browInnerUp", 0.85), ("jawOpen", 0.60)],
}

# Expression override modes (add-on enums 'none' | 'block' | 'blend', probed live 2026-09-07).
# Semantics: overrideX set on expression E suppresses X while E is active. So they go on the
# expressions that would otherwise SUM with a tracker-driven channel -- never on the raw ARKit
# customs, which ARE the tracker's channel and must not fight it.
PRESET_OVERRIDES = {
    # eyes shut => whatever the gaze solver says is irrelevant
    "blink":       {"override_look_at": "block"},
    "blink_left":  {"override_look_at": "block"},
    "blink_right": {"override_look_at": "block"},
    # emotions move the mouth, so a viseme must not stack on top of them at full strength
    "happy":     {"override_mouth": "blend", "override_blink": "blend"},
    "relaxed":   {"override_mouth": "blend", "override_blink": "blend"},
    "angry":     {"override_mouth": "blend"},
    "sad":       {"override_mouth": "blend"},
    # eyes wide: a blink on top would fight it outright, and the jaw is already driven here
    "surprised": {"override_mouth": "blend", "override_blink": "block"},
}


# Peak displacement each authored shape ASKS for, in metres. WI 1362 recorded `browInnerUp` delivering
# 8.7 mm against a 30 mm request -- an elliptical falloff multiplied by an inner taper -- wrote it into
# test.md as a finding, and shipped anyway. A finding that does not become a gate is a finding that
# recurs, and it did: the brows read as dead the moment a real tracker touched the file.
NOMINAL_MM = {
    "eyeBlinkLeft": 19.0, "eyeBlinkRight": 19.0, "eyeWideLeft": 15.0, "eyeWideRight": 15.0,
    "eyeSquintLeft": 13.0, "eyeSquintRight": 13.0,
    "browInnerUp": 30.0, "browDownLeft": 26.0, "browDownRight": 26.0,
    "browOuterUpLeft": 26.0, "browOuterUpRight": 26.0,
    "jawOpen": 43.0, "jawLeft": 14.0, "jawRight": 14.0,
    "mouthSmileLeft": 28.0, "mouthSmileRight": 28.0,
    "mouthFrownLeft": 26.0, "mouthFrownRight": 26.0,
    "mouthFunnel": 22.0, "mouthPucker": 30.0,
    "mouthUpperUpLeft": 16.0, "mouthUpperUpRight": 16.0,
    "mouthLowerDownLeft": 18.0, "mouthLowerDownRight": 18.0,
    "mouthStretchLeft": 20.0, "mouthStretchRight": 20.0,
    "mouthLeft": 16.0, "mouthRight": 16.0, "mouthClose": 14.0,
}
# A shape must deliver at least this fraction of its nominal, or the mask is eating the amplitude.
NOMINAL_FLOOR = 0.60

# The six L/R pairs added by WI 1363. Asymmetry is where Perfect Sync visibly beats presets, so driving
# one side must leave the other alone -- checked, not assumed.
ASYMMETRIC_PAIRS_V2 = ("browOuterUp", "mouthUpperUp", "mouthLowerDown", "mouthStretch")


def stub_names(authored):
    """The declared-but-empty clips, given the authored set."""
    return tuple(n for n in ARKIT_52 if n not in set(authored))


def check_contract(authored=STYLIZED_V1_AUTHORED):
    """Validate the contract table itself, independently of any mesh. Returns a list of problems;
    empty means consistent. Called by the generator before it builds anything, so a table typo fails
    in a second rather than after a full export."""
    problems = []
    if len(ARKIT_52) != 52:
        problems.append(f"ARKIT_52 has {len(ARKIT_52)} names, expected 52")
    if len(set(ARKIT_52)) != len(ARKIT_52):
        problems.append("ARKIT_52 contains duplicates")
    if len(VRM1_PRESETS) != 18:
        problems.append(f"VRM1_PRESETS has {len(VRM1_PRESETS)} slots, expected 18")

    known = set(ARKIT_52)
    for name in authored:
        if name not in known:
            problems.append(f"authored shape {name!r} is not an ARKit-52 name")

    # every one of the 52 is either authored or has a recorded stub reason, exactly once
    accounted = {}
    for reason, names in STUB_REASONS.items():
        for n in names:
            if n in accounted:
                problems.append(f"{n!r} has two stub reasons: {accounted[n]} and {reason}")
            accounted[n] = reason
        for n in names:
            if n not in known:
                problems.append(f"stub reason {reason!r} names {n!r}, not an ARKit-52 name")
    for n in ARKIT_52:
        if n in set(authored):
            if n in accounted:
                problems.append(f"{n!r} is both authored and listed as a stub")
        elif n not in accounted:
            problems.append(f"{n!r} is neither authored nor given a stub reason")

    for preset, binds in PRESET_COMPOSITION.items():
        if preset not in VRM1_PRESETS:
            problems.append(f"composed preset {preset!r} is not a VRM 1.0 preset slot")
        for shape, weight in binds:
            if shape not in set(authored):
                problems.append(f"preset {preset!r} binds unauthored shape {shape!r}")
            if not 0.0 < weight <= 1.0:
                problems.append(f"preset {preset!r} binds {shape!r} at out-of-range weight {weight}")
    for name in authored:
        if name not in NOMINAL_MM:
            problems.append(f"authored shape {name!r} has no NOMINAL_MM entry to be checked against")
    for preset in PRESET_OVERRIDES:
        if preset not in PRESET_COMPOSITION:
            problems.append(f"override set on {preset!r}, which composes nothing")
    return problems


if __name__ == "__main__":
    found = check_contract()
    for p in found:
        print("PROBLEM:", p)
    print(f"arkit52: {len(ARKIT_52)} clips, {len(STYLIZED_V1_AUTHORED)} authored, "
          f"{len(stub_names(STYLIZED_V1_AUTHORED))} stubs, "
          f"{len(PRESET_COMPOSITION)} of {len(VRM1_PRESETS)} presets composed — "
          f"{'OK' if not found else 'FAILED'}")
    raise SystemExit(1 if found else 0)
