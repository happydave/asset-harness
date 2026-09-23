#!/usr/bin/env python3
"""Convert a ComfyUI UI-format template into an API graph, using the server's /object_info schemas.

    template_to_api.py TEMPLATE OBJECT_INFO OUT.json --image NAME --prefix PREFIX
                       [--set NODE_ID=VALUE ...] [--diff GRAPH.json]

Widget values are matched to schema inputs in order. A seed-style INT with `control_after_generate`
carries one extra value, a COMFY_DYNAMICCOMBO_V3 is followed by its chosen option's sub-widgets
(sent as `name.sub`), and an image-upload combo carries one extra value. A node whose values do not
fit its schema stops the conversion: a guessed mapping would run the wrong settings silently.

Primitive and switch nodes are resolved to constants and their sources, preview nodes become
SaveImage (or are dropped for 3D previews), and everything not upstream of an output is pruned.
`--set` overrides a node's value: `316=true` flips the template's arm switch, `3=57` a sampler's seed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COLOR", "COMFY_DYNAMICCOMBO_V3", "LOAD_3D"}
PRIMITIVES = {"PrimitiveInt", "PrimitiveFloat", "PrimitiveBoolean", "PrimitiveString", "PrimitiveStringMultiline"}
DROP = {"Note", "MarkdownNote", "Preview3DAdvanced", "Preview3D"}
IMAGE_PREVIEWS = {"PreviewImage", "MaskPreview"}


class ConversionError(SystemExit):
    pass


def _spec_type(spec):
    head = spec[0]
    return "COMBO" if isinstance(head, list) else head


def _opts(spec):
    return spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}


def _schema_inputs(schema):
    """(name, spec) for every declared input, in the server's input_order."""
    order = schema.get("input_order") or {}
    out = []
    for section in ("required", "optional"):
        specs = schema.get("input", {}).get(section, {})
        for name in order.get(section, list(specs)):
            out.append((name, specs[name]))
    return out


def _cast(value, typ):
    if typ == "INT" and isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if typ == "FLOAT" and isinstance(value, (str, int)) and not isinstance(value, bool):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def map_widgets(node, schema):
    """{input name: value} for a node's widgets, or raise naming the node."""
    values = list(node.get("widgets_values") or [])
    if isinstance(node.get("widgets_values"), dict):
        raise ConversionError(f"node {node['id']} {node['type']}: dict widgets_values not supported")
    out, i = {}, 0
    for name, spec in _schema_inputs(schema):
        typ, opts = _spec_type(spec), _opts(spec)
        if typ not in WIDGET_TYPES:
            continue
        if i >= len(values):
            raise ConversionError(f"node {node['id']} {node['type']}: no widget value for {name!r}")
        value = values[i]; i += 1
        if typ == "COMFY_DYNAMICCOMBO_V3":
            out[name] = value
            option = next((o for o in opts.get("options", []) if o.get("key") == value), None)
            if option is None:
                raise ConversionError(f"node {node['id']} {node['type']}: {name}={value!r} is not an option")
            for sub, sub_spec in option.get("inputs", {}).get("required", {}).items():
                if i >= len(values):
                    raise ConversionError(f"node {node['id']} {node['type']}: no value for {name}.{sub}")
                out[f"{name}.{sub}"] = _cast(values[i], _spec_type(sub_spec)); i += 1
            continue
        out[name] = _cast(value, typ)
        if typ == "INT" and opts.get("control_after_generate"):
            i += 1
        if typ == "COMBO" and opts.get("image_upload"):
            i += 1
    if i != len(values):
        raise ConversionError(f"node {node['id']} {node['type']}: {len(values)} widget values, schema "
                              f"accounts for {i}: {values!r}")
    return out


def convert(template, object_info, image, prefix, overrides):
    nodes = {n["id"]: n for n in template["nodes"]}
    links = {l[0]: l for l in template["links"]}  # id -> [id, from, from_slot, to, to_slot, type]

    for nid, raw in overrides.items():
        n = nodes[nid]
        vals = list(n.get("widgets_values") or [])
        vals[0] = json.loads(raw) if raw in ("true", "false") or re.fullmatch(r"-?\d+(\.\d+)?", raw) else raw
        n["widgets_values"] = vals

    for n in nodes.values():
        if n.get("mode", 0) != 0:
            raise ConversionError(f"node {n['id']} {n['type']}: mode {n['mode']} (muted/bypassed) not supported")
        if n["type"] not in object_info and n["type"] not in DROP:
            raise ConversionError(f"node {n['id']}: type {n['type']!r} is not on this server")

    def source(link_id):
        """(node id, slot) a link ultimately comes from, through switches; or ('const', value)."""
        _, src, slot, *_ = links[link_id]
        n = nodes[src]
        if n["type"] in IMAGE_PREVIEWS:
            # This frontend's preview nodes also pass their input through; follow it.
            passed = next((i.get("link") for i in n.get("inputs", []) if i["name"] in ("images", "mask")), None)
            if passed is None:
                raise ConversionError(f"preview {src}: consumed but has no input")
            return source(passed)
        if n["type"] in PRIMITIVES:
            return ("const", map_widgets(n, object_info[n["type"]])["value"])
        if n["type"] == "ComfySwitchNode":
            by_name = {i["name"]: i for i in n.get("inputs", [])}
            sw = by_name.get("switch", {}).get("link")
            flag = source(sw)[1] if sw is not None else map_widgets(n, object_info[n["type"]])["switch"]
            if not isinstance(flag, bool):
                raise ConversionError(f"switch {src}: non-constant switch value {flag!r}")
            chosen = by_name["on_true" if flag else "on_false"].get("link")
            if chosen is None:
                raise ConversionError(f"switch {src}: the chosen branch is unconnected")
            return source(chosen)
        return (src, slot)

    graph = {}
    for n in nodes.values():
        t = n["type"]
        if t in DROP or t in PRIMITIVES or t == "ComfySwitchNode" or t == "GetNode" or t == "SetNode":
            continue
        schema = object_info[t]
        inputs = map_widgets(n, schema)
        for inp in n.get("inputs", []):
            if inp.get("link") is None:
                continue
            src = source(inp["link"])
            inputs[inp["name"]] = src[1] if src[0] == "const" else [str(src[0]), src[1]]
        cls = t
        if t in IMAGE_PREVIEWS:
            label = re.sub(r"[^A-Za-z0-9]+", "_", n.get("title") or f"n{n['id']}").strip("_").lower()
            if t == "MaskPreview":
                graph[f"{n['id']}m"] = {"class_type": "MaskToImage", "inputs": {"mask": inputs.pop("mask")}}
                inputs = {"images": [f"{n['id']}m", 0]}
            cls, inputs = "SaveImage", {"images": inputs["images"], "filename_prefix": f"{prefix}_{label}"}
        if t == "LoadImage":
            inputs["image"] = image
        if "filename_prefix" in inputs and t not in IMAGE_PREVIEWS:
            inputs["filename_prefix"] = prefix
        graph[str(n["id"])] = {"class_type": cls, "inputs": inputs}

    # Keep only what an output needs.
    outputs = [k for k, v in graph.items()
               if v["class_type"] == "SaveImage" or object_info.get(v["class_type"], {}).get("output_node")]
    keep, stack = set(), list(outputs)
    while stack:
        k = stack.pop()
        if k in keep:
            continue
        keep.add(k)
        for v in graph[k]["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                stack.append(v[0])
    return {k: graph[k] for k in sorted(keep, key=lambda s: (len(s), s))}


def diff(converted, reference):
    """Differences on the reference's nodes: class, literal inputs, then link inputs."""
    lines = []
    for k, ref in reference.items():
        got = converted.get(k)
        if got is None:
            lines.append(f"{k} {ref['class_type']}: missing"); continue
        if got["class_type"] != ref["class_type"]:
            lines.append(f"{k}: class {got['class_type']} != {ref['class_type']}")
        for name in sorted(set(ref["inputs"]) | set(got["inputs"])):
            a, b = got["inputs"].get(name), ref["inputs"].get(name)
            if a != b:
                kind = "link" if isinstance(a, list) or isinstance(b, list) else "literal"
                lines.append(f"{k} {ref['class_type']}.{name} [{kind}]: converted {a!r} reference {b!r}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("template"); ap.add_argument("object_info"); ap.add_argument("out")
    ap.add_argument("--image", required=True); ap.add_argument("--prefix", required=True)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--diff")
    a = ap.parse_args(argv)
    overrides = {int(k): v for k, v in (s.split("=", 1) for s in a.set)}
    graph = convert(json.load(open(a.template)), json.load(open(a.object_info)), a.image, a.prefix, overrides)
    json.dump(graph, open(a.out, "w"), indent=1)
    print(f"{len(graph)} nodes -> {a.out}")
    if a.diff:
        lines = diff(graph, json.load(open(a.diff)))
        print(f"diff against {a.diff}: {len(lines)} difference(s)")
        for line in lines:
            print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
