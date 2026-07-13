"""Dependency-free JSON Schema (draft-07) subset validator for Asset Studio contracts.

This module is vendored into asset-harness (contracts/) so manifest validation runs
with plain host python3 and no third-party imports (WI 902 invariant 3). It implements
exactly the constructs used by contracts-1.schema.json:

    type (string or list), required, properties, additionalProperties (bool or schema),
    patternProperties, propertyNames, enum, const, pattern, items (single schema),
    oneOf, anyOf, allOf, not, $ref (within-document only), minimum, maximum,
    exclusiveMinimum, minLength, minItems

Anything else present in a schema raises UnsupportedKeyword rather than being silently
ignored, so validator/schema drift is loud. Correctness is cross-checked against the
`jsonschema` library by the contracts test suite (test_contracts_python.py); the vendored
copy runs standalone.

Semantics notes (mirrors JSON Schema, not Python intuition):
- `pattern` is a substring search (re.search), matching ECMA `pattern` semantics.
- Python bools are NOT integers/numbers here, and `const: 1` does not match `true`.
- An integral float (e.g. 1.0) IS a valid `integer`, per draft-06+ (matches ajv/jsonschema).
"""

import re

# Keywords that shape validation. Annotation-only keys are ignored deliberately.
_ANNOTATIONS = {
    "$schema", "$id", "$comment", "title", "description", "definitions",
    "default", "examples",
}
_SUPPORTED = {
    "type", "required", "properties", "additionalProperties", "patternProperties",
    "propertyNames", "enum", "const", "pattern", "items", "oneOf", "anyOf", "allOf",
    "not", "$ref", "minimum", "maximum", "exclusiveMinimum", "minLength", "minItems",
}


class UnsupportedKeyword(Exception):
    pass


def _type_ok(value, tname):
    if tname == "object":
        return isinstance(value, dict)
    if tname == "array":
        return isinstance(value, list)
    if tname == "string":
        return isinstance(value, str)
    if tname == "integer":
        # draft-06+: a number with a zero fractional part IS an integer (1.0 matches).
        # Mirrors both ajv and the `jsonschema` library; a stricter check here would
        # make the harness gate reject documents the studio suite accepts.
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if tname == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if tname == "boolean":
        return isinstance(value, bool)
    if tname == "null":
        return value is None
    raise UnsupportedKeyword("unknown type name: %s" % tname)


def _json_equal(a, b):
    # bool/number distinction: True != 1 for enum/const purposes.
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise UnsupportedKeyword("only within-document $ref supported: %s" % ref)
    node = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[token]
    return node


def validate(root, schema, instance, path="$"):
    """Return a list of error strings ('' means valid). root is the whole schema doc."""
    errors = []

    if "$ref" in schema:
        target = _resolve_ref(root, schema["$ref"])
        errors.extend(validate(root, target, instance, path))
        rest = {k: v for k, v in schema.items() if k != "$ref" and k not in _ANNOTATIONS}
        if rest:
            errors.extend(validate(root, rest, instance, path))
        return errors

    for key in schema:
        if key not in _SUPPORTED and key not in _ANNOTATIONS:
            raise UnsupportedKeyword("keyword %r at %s is not supported" % (key, path))

    t = schema.get("type")
    if t is not None:
        names = t if isinstance(t, list) else [t]
        if not any(_type_ok(instance, n) for n in names):
            errors.append("%s: expected type %s" % (path, "/".join(names)))
            return errors  # structural mismatch; deeper checks would be noise

    if "enum" in schema:
        if not any(_json_equal(instance, allowed) for allowed in schema["enum"]):
            errors.append("%s: value not in enum %s" % (path, schema["enum"]))
    if "const" in schema:
        if not _json_equal(instance, schema["const"]):
            errors.append("%s: expected const %r" % (path, schema["const"]))

    if isinstance(instance, str):
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append("%s: does not match pattern %s" % (path, schema["pattern"]))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than minLength %d" % (path, schema["minLength"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: below minimum %s" % (path, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: above maximum %s" % (path, schema["maximum"]))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append("%s: not above exclusiveMinimum %s" % (path, schema["exclusiveMinimum"]))

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append("%s: missing required property %r" % (path, req))
        props = schema.get("properties", {})
        patprops = schema.get("patternProperties", {})
        for name, value in instance.items():
            child = "%s.%s" % (path, name)
            matched = False
            if name in props:
                matched = True
                errors.extend(validate(root, props[name], value, child))
            for pat, sub in patprops.items():
                if re.search(pat, name):
                    matched = True
                    errors.extend(validate(root, sub, value, child))
            if not matched and "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is False:
                    errors.append("%s: additional property %r not allowed" % (path, name))
                elif isinstance(ap, dict):
                    errors.extend(validate(root, ap, value, child))
        if "propertyNames" in schema:
            for name in instance:
                sub_errors = validate(root, schema["propertyNames"], name,
                                      "%s.(propertyName %r)" % (path, name))
                errors.extend(sub_errors)

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than minItems %d" % (path, schema["minItems"]))
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(validate(root, schema["items"], item, "%s[%d]" % (path, i)))

    if "allOf" in schema:
        for sub in schema["allOf"]:
            errors.extend(validate(root, sub, instance, path))
    if "anyOf" in schema:
        branches = [validate(root, sub, instance, path) for sub in schema["anyOf"]]
        if not any(not b for b in branches):
            errors.append("%s: no anyOf branch matched" % path)
    if "oneOf" in schema:
        branch_errors = [validate(root, sub, instance, path) for sub in schema["oneOf"]]
        valid_count = sum(1 for b in branch_errors if not b)
        if valid_count != 1:
            errors.append("%s: oneOf matched %d branches (need exactly 1)" % (path, valid_count))
            if valid_count == 0:
                # Surface the closest branch's errors so the actual defect is named.
                errors.extend(min(branch_errors, key=len))
    if "not" in schema:
        if not validate(root, schema["not"], instance, path):
            errors.append("%s: matches disallowed ('not') schema" % path)

    return errors


def validate_ref(root, ref, instance):
    """Validate instance against a definition reference like '#/definitions/sidecarManifest'."""
    return validate(root, {"$ref": ref}, instance)
