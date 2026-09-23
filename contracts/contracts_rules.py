"""Cross-field rules for `rigged-avatar` entries that JSON Schema cannot express (WI 1368).

The schema fixes each block's shape; these rules relate the blocks to each other and to the rig's
bone list. Stdlib only, pure: `check(entry)` returns a list of error strings, empty when clean.
Each error starts with its rule id (R1..R4) and names the offending value, so a test can assert
the rule that fired. Vendored into asset-harness beside the validator; the TypeScript twin in
`src/rules.ts` is held to the same fixtures.

Rules apply only to the blocks that are present: an entry without them (the rigid prototypes)
passes with no errors, and an entry of any other class is not judged at all.
"""


def _names(values):
    return [v for v in (values or []) if isinstance(v, str)]


def check(entry):
    if not isinstance(entry, dict) or entry.get("class") != "rigged-avatar":
        return []
    errors = []
    bones = set(_names(entry.get("bones"))) if isinstance(entry.get("bones"), list) else None
    humanoid = entry.get("humanoid") if isinstance(entry.get("humanoid"), dict) else None
    expressions = entry.get("expressions") if isinstance(entry.get("expressions"), dict) else None
    presets = entry.get("presets") if isinstance(entry.get("presets"), dict) else None
    gaze = entry.get("gaze") if isinstance(entry.get("gaze"), dict) else None
    springs = entry.get("springs") if isinstance(entry.get("springs"), dict) else None

    # R1 — humanoid <-> rig: every mapped key is a rig bone; gaze bones are rig bones; gaze slots are mapped.
    if humanoid is not None and bones is not None:
        for our in sorted(humanoid):
            if our not in bones:
                errors.append("R1: humanoid maps %r, which is not in bones" % our)
    if gaze is not None:
        if bones is not None:
            for b in _names(gaze.get("bones")):
                if b not in bones:
                    errors.append("R1: gaze.bones names %r, which is not in bones" % b)
        if humanoid is not None:
            mapped = set(v for v in humanoid.values() if isinstance(v, str))
            for slot in _names(gaze.get("humanoid_slots")):
                if slot not in mapped:
                    errors.append("R1: gaze.humanoid_slots names %r, which humanoid does not map" % slot)

    # R2 — the split: authored and the stubs partition declared; nominal_mm keys are authored.
    if expressions is not None:
        declared = _names(expressions.get("declared"))
        authored = _names(expressions.get("authored"))
        stubs = expressions.get("stubs") if isinstance(expressions.get("stubs"), dict) else {}
        stubbed = []
        for reason, names in sorted(stubs.items()):
            stubbed.extend(_names(names))
        for n in sorted(set(authored) & set(stubbed)):
            errors.append("R2: %r is both authored and a stub" % n)
        for n in sorted(set(authored) | set(stubbed)):
            if n not in set(declared):
                errors.append("R2: %r is authored or stubbed but not declared" % n)
        for n in sorted(set(declared) - set(authored) - set(stubbed)):
            errors.append("R2: %r is declared but neither authored nor given a stub reason" % n)
        if len(set(stubbed)) != len(stubbed):
            dupes = sorted(n for n in set(stubbed) if stubbed.count(n) > 1)
            errors.append("R2: stub names listed under two reasons: %s" % dupes)
        nominal = expressions.get("nominal_mm") if isinstance(expressions.get("nominal_mm"), dict) else {}
        for n in sorted(nominal):
            if n not in set(authored):
                errors.append("R2: nominal_mm names %r, which is not authored" % n)

    # R3 — presets: composed binds only authored shapes; composed and empty_by_design are disjoint;
    # overrides sit on composed presets.
    if presets is not None:
        composed = presets.get("composed") if isinstance(presets.get("composed"), dict) else {}
        empty = _names(presets.get("empty_by_design"))
        authored = set(_names(expressions.get("authored"))) if expressions is not None else None
        for preset, binds in sorted(composed.items()):
            for b in binds if isinstance(binds, list) else []:
                shape = b.get("shape") if isinstance(b, dict) else None
                if authored is not None and shape not in authored:
                    errors.append("R3: preset %r binds %r, which is not authored" % (preset, shape))
        for p in sorted(set(composed) & set(empty)):
            errors.append("R3: preset %r is both composed and empty_by_design" % p)
        overrides = presets.get("overrides") if isinstance(presets.get("overrides"), dict) else {}
        for p in sorted(overrides):
            if p not in composed:
                errors.append("R3: overrides set on %r, which composes nothing" % p)

    # R4 — springs: joints, centers and collider bones are rig bones; groups and colliders resolve;
    # names are unique.
    if springs is not None:
        colliders = [c for c in (springs.get("colliders") or []) if isinstance(c, dict)]
        groups = springs.get("collider_groups") if isinstance(springs.get("collider_groups"), dict) else {}
        chains = [c for c in (springs.get("chains") or []) if isinstance(c, dict)]
        collider_names = [c.get("name") for c in colliders]
        if len(set(collider_names)) != len(collider_names):
            errors.append("R4: collider names are not unique: %s" % sorted(set(n for n in collider_names if collider_names.count(n) > 1)))
        chain_names = [c.get("name") for c in chains]
        if len(set(chain_names)) != len(chain_names):
            errors.append("R4: chain names are not unique: %s" % sorted(set(n for n in chain_names if chain_names.count(n) > 1)))
        if bones is not None:
            for c in colliders:
                if c.get("bone") not in bones:
                    errors.append("R4: collider %r sits on %r, which is not in bones" % (c.get("name"), c.get("bone")))
            for ch in chains:
                for j in _names(ch.get("joints")):
                    if j not in bones:
                        errors.append("R4: chain %r joint %r is not in bones" % (ch.get("name"), j))
                center = ch.get("center")
                if isinstance(center, str) and center not in bones:
                    errors.append("R4: chain %r center %r is not in bones" % (ch.get("name"), center))
        for g, members in sorted(groups.items()):
            for m in _names(members):
                if m not in set(collider_names):
                    errors.append("R4: collider group %r names collider %r, which does not exist" % (g, m))
        for ch in chains:
            for g in _names(ch.get("collider_groups")):
                if g not in groups:
                    errors.append("R4: chain %r references collider group %r, which does not exist" % (ch.get("name"), g))
    return errors
