#!/usr/bin/env python3
"""Headless validation gate for exported VRM avatars.

    python3 vrm_gate.py AVATAR.vrm [--vrm0 AVATAR.vrm0.vrm] [--archetype NAME] [--out DIR]
                                   [--no-validator] [--no-browser]

Three stages, cheapest first:
  validator  Khronos glTF-Validator over the container and its buffers (vendor/, see fetch_vendor.sh)
  contract   the head-archetype contract read straight from the file: names, binds, displacement,
             presets, humanoid, coordinate frame (stdlib only)
  consumer   three-vrm in headless Chromium: what a runtime resolves, plus a contact sheet

Exits 0 only when every stage that was asked for ran to completion and every check passed. A stage
that cannot run fails the gate; `--no-validator` / `--no-browser` switch a stage off, and the report
says so. The contact sheet is for human eyes: pixel checks assert changed / unchanged, never quality.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import arkit52  # noqa: E402
from glb import Glb, GlbError  # noqa: E402

PASS, FAIL, NOT_RUN = "pass", "fail", "not-run"

# VRM 1.0's required humanoid bones, as the file spells them (VRMC_vrm humanoid.humanBones keys).
VRM1_REQUIRED_BONES = (
    "hips", "spine", "head",
    "leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand",
    "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot",
)
# VRM 0.x preset names for the 1.0 presets that have one; `surprised` is new in 1.0.
VRM0_PRESET = {
    "blink": "blink", "blink_left": "blink_l", "blink_right": "blink_r",
    "aa": "a", "ih": "i", "ou": "u", "ee": "e", "oh": "o",
    "happy": "joy", "angry": "angry", "sad": "sorrow", "relaxed": "fun",
}
OVERRIDE_FIELDS = ("overrideBlink", "overrideLookAt", "overrideMouth")
EVIDENCE_ROW = re.compile(r"^authored morph (\w+) reaches its nominal amplitude$")
EVIDENCE_MM = re.compile(r"^(\d+(?:\.\d+)?) mm of ")


class Report:
    def __init__(self):
        self.rows = []
        self.stages = {}

    def add(self, stage, name, ok, detail=""):
        return self._row(stage, name, PASS if ok else FAIL, detail)

    def not_run(self, stage, name, reason):
        return self._row(stage, name, NOT_RUN, reason)

    def _row(self, stage, name, status, detail):
        self.rows.append({"stage": stage, "check": name, "status": status, "detail": detail})
        tag = {PASS: "PASS", FAIL: "FAIL", NOT_RUN: "NOT RUN"}[status]
        print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
        return status == PASS

    def guarded(self, stage, name, fn):
        """Run one check; a missing input is that check's failure, never a traceback."""
        try:
            ok, detail = fn()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, GlbError) as e:
            ok, detail = False, f"could not evaluate: {type(e).__name__}: {e}"
        return self.add(stage, name, ok, detail)

    def count(self, status):
        return sum(1 for r in self.rows if r["status"] == status)

    @property
    def ok(self):
        return self.count(FAIL) == 0 and all(s == "ran" or s == "off" for s in self.stages.values())


# ---- stage: contract -------------------------------------------------------------------------------
class Vrm1:
    """The parts of a VRM 1.0 file the contract checks read, resolved once."""

    def __init__(self, glb):
        self.glb = glb
        j = glb.json
        self.vrm = j["extensions"]["VRMC_vrm"]
        self.nodes = j.get("nodes", [])
        self.meshes = j.get("meshes", [])
        self._disp = {}

    def target_names(self, mesh_index):
        return (self.meshes[mesh_index].get("extras") or {}).get("targetNames")

    def resolve(self, bind):
        """(mesh index, target index, target name) for a morphTargetBind, or raise with the reason."""
        node = bind["node"]
        if not 0 <= node < len(self.nodes) or "mesh" not in self.nodes[node]:
            raise ValueError(f"bind node {node} is not a mesh node")
        mesh_index = self.nodes[node]["mesh"]
        index = bind["index"]
        for p, prim in enumerate(self.meshes[mesh_index]["primitives"]):
            if not 0 <= index < len(prim.get("targets", [])):
                raise ValueError(f"target index {index} is out of range on primitive {p} of mesh "
                                 f"{self.meshes[mesh_index].get('name')!r}")
        names = self.target_names(mesh_index)
        if not names or index >= len(names):
            raise ValueError(f"mesh {self.meshes[mesh_index].get('name')!r} has no targetNames entry {index}")
        return mesh_index, index, names[index]

    def displacement_mm(self, mesh_index, target_index):
        """Largest vertex delta of one morph target across the mesh's primitives, from the buffer."""
        key = (mesh_index, target_index)
        if key not in self._disp:
            best = 0.0
            for prim in self.meshes[mesh_index]["primitives"]:
                best = max(best, self.glb.max_vec3_length(prim["targets"][target_index]["POSITION"]))
            self._disp[key] = best * 1000.0
        return self._disp[key]

    def bind_map(self, expression):
        """{target name: weight} for an expression's binds."""
        out = {}
        for bind in expression.get("morphTargetBinds", []):
            _, _, name = self.resolve(bind)
            out[name] = out.get(name, 0.0) + bind.get("weight", 1.0)
        return out


def check_container(report, path):
    """Returns the parsed Glb, or None with one failed row."""
    try:
        glb = Glb.load(path)
    except (OSError, GlbError) as e:
        report.add("contract", f"{path.name} is a readable GLB", False, str(e))
        return None
    kinds = [k.decode("latin-1").rstrip("\x00") for k, _, _ in glb.chunks]
    report.add("contract", f"{path.name} is a readable GLB", glb.bin is not None,
               f"chunks {kinds}, {sum(n for _, _, n in glb.chunks):,} payload bytes")
    return glb if glb.bin is not None else None


def check_vrm1(report, glb, archetype, evidence):
    st = "contract"
    authored = arkit52.ARCHETYPES[archetype]
    stubs = arkit52.stub_names(authored)
    j = glb.json

    def declared():
        used = j.get("extensionsUsed", [])
        spec = (j.get("extensions") or {}).get("VRMC_vrm", {}).get("specVersion")
        return ("VRMC_vrm" in used and spec == "1.0", f"extensionsUsed {used}, specVersion {spec!r}")
    if not report.guarded(st, "the file declares VRMC_vrm 1.0", declared):
        for name in ("expression names", "bind resolution", "displacement", "presets", "humanoid", "frame"):
            report.not_run(st, name, "no VRMC_vrm 1.0 extension to read")
        return None
    v = Vrm1(glb)
    ex = v.vrm.get("expressions", {})
    preset, custom = ex.get("preset", {}), ex.get("custom", {})

    want_presets = sorted(arkit52.vrm1_json_key(p) for p in arkit52.VRM1_PRESETS)
    report.add(st, "presets are exactly the 18 VRM 1.0 slots", sorted(preset) == want_presets,
               _set_diff(preset, want_presets))
    report.add(st, "customs are exactly the 52 ARKit names, exact case",
               sorted(custom) == sorted(arkit52.ARKIT_52), _set_diff(custom, arkit52.ARKIT_52))

    def names_table():
        mesh_index = _morph_mesh(v, archetype)
        names = v.target_names(mesh_index)
        counts = {len(p.get("targets", [])) for p in v.meshes[mesh_index]["primitives"]}
        ok = bool(names) and counts == {len(names)} and len(set(names)) == len(names)
        return ok, f"{len(names or [])} targetNames, per-primitive target counts {sorted(counts)}"
    report.guarded(st, "the morph mesh names every target once", names_table)

    def all_resolve():
        n = 0
        for group in (preset, custom):
            for name, e in group.items():
                for bind in e.get("morphTargetBinds", []):
                    try:
                        v.resolve(bind)
                    except ValueError as err:
                        return False, f"{name}: {err}"
                    n += 1
        return n > 0, f"{n} binds resolve to a mesh node and an in-range target"
    report.guarded(st, "every morphTargetBind resolves", all_resolve)

    bound = sorted(n for n, e in custom.items() if e.get("morphTargetBinds"))
    report.add(st, "the bound customs are exactly the archetype's authored set", bound == sorted(authored),
               f"{len(bound)} bound; " + _set_diff(bound, authored))
    unbound = sorted(n for n, e in custom.items() if not e.get("morphTargetBinds"))
    report.add(st, "the remaining customs are exactly the declared stubs",
               sorted(set(custom) - set(authored)) == sorted(stubs),
               f"{len(unbound)} without binds; " + _set_diff(set(custom) - set(authored), stubs))

    for name in authored:
        def one_to_one(name=name):
            binds = custom[name].get("morphTargetBinds", [])
            if len(binds) != 1:
                return False, f"{len(binds)} binds, expected exactly 1"
            _, _, target = v.resolve(binds[0])
            weight = binds[0].get("weight", 1.0)
            return (target == name and abs(weight - 1.0) < 1e-6,
                    f"binds target {target!r} at weight {weight}")
        report.guarded(st, f"{name} binds its own morph, 1:1", one_to_one)

    for name in authored:
        def displaces(name=name):
            nominal = arkit52.NOMINAL_MM[name]
            floor = nominal * arkit52.NOMINAL_FLOOR
            mesh_index, index, _ = v.resolve(custom[name]["morphTargetBinds"][0])
            mm = v.displacement_mm(mesh_index, index)
            return mm >= floor, f"{mm:.2f} mm in the file; floor {floor:.1f} mm ({nominal:.0f} mm nominal)"
        report.guarded(st, f"{name} displaces (authored)", displaces)

    for name in stubs:
        def flat(name=name):
            binds = custom[name].get("morphTargetBinds", [])
            total = 0.0
            for bind in binds:
                mesh_index, index, _ = v.resolve(bind)
                total += abs(bind.get("weight", 1.0)) * v.displacement_mm(mesh_index, index)
            return total == 0.0, f"{total!r} mm over {len(binds)} bind(s)"
        report.guarded(st, f"{name} displaces by exactly zero (stub)", flat)

    def no_orphans():
        names = v.target_names(_morph_mesh(v, archetype)) or []
        extra = sorted(set(names) - set(authored))
        return not extra, f"{len(names)} targets" + (f"; not in the authored set: {extra}" if extra else "")
    report.guarded(st, "every morph target is an authored shape", no_orphans)

    for attr, binds in arkit52.PRESET_COMPOSITION.items():
        def composed(attr=attr, binds=binds):
            got = v.bind_map(preset[arkit52.vrm1_json_key(attr)])
            want = dict(binds)
            ok = set(got) == set(want) and all(abs(got[k] - want[k]) < 1e-6 for k in want)
            return ok, json.dumps({k: round(w, 4) for k, w in sorted(got.items())})
        report.guarded(st, f"preset {arkit52.vrm1_json_key(attr)} is composed as the contract says", composed)

    def empties():
        names = [arkit52.vrm1_json_key(p) for p in arkit52.VRM1_PRESETS if p not in arkit52.PRESET_COMPOSITION]
        loaded = [n for n in names if preset[n].get("morphTargetBinds")]
        return not loaded, f"{names} carry no binds" if not loaded else f"unexpected binds on {loaded}"
    report.guarded(st, "neutral and the look presets are empty (gaze is bone-driven)", empties)

    def overrides():
        wrong = []
        for attr in arkit52.VRM1_PRESETS:
            want = {f: "none" for f in OVERRIDE_FIELDS}
            want.update({arkit52.vrm1_json_key(k): val
                         for k, val in arkit52.PRESET_OVERRIDES.get(attr, {}).items()})
            e = preset[arkit52.vrm1_json_key(attr)]
            got = {f: e.get(f, "none") for f in OVERRIDE_FIELDS}
            if got != want:
                wrong.append(f"{attr}: {got}")
        return not wrong, "; ".join(wrong) or f"{len(arkit52.PRESET_OVERRIDES)} presets carry overrides"
    report.guarded(st, "override modes match the contract", overrides)

    bones = v.vrm.get("humanoid", {}).get("humanBones", {})

    def humanoid():
        missing = [b for b in VRM1_REQUIRED_BONES + ("leftEye", "rightEye")
                   if not isinstance(bones.get(b, {}).get("node"), int)
                   or not 0 <= bones[b]["node"] < len(v.nodes)]
        return not missing, f"{len(bones)} bones mapped" + (f"; missing {missing}" if missing else "")
    report.guarded(st, "the 15 required humanoid bones and both eyes name a node", humanoid)

    def distinct():
        seen = {}
        for bone, entry in bones.items():
            seen.setdefault(entry["node"], []).append(bone)
        shared = {n: b for n, b in seen.items() if len(b) > 1}
        return not shared, f"nodes filling two slots: {shared}" if shared else f"{len(seen)} distinct nodes"
    report.guarded(st, "no node fills two humanoid slots", distinct)

    look = v.vrm.get("lookAt", {})
    report.add(st, "lookAt is bone-driven", look.get("type") == "bone", f"type {look.get('type')!r}")

    def positions():
        return (glb.world_position(bones["leftEye"]["node"]), glb.world_position(bones["rightEye"]["node"]),
                glb.world_position(bones["head"]["node"]))

    def faces_z():
        le, re_, hd = positions()
        return (le[2] > hd[2] and re_[2] > hd[2],
                f"eyes at z = {le[2] * 1000:.1f} / {re_[2] * 1000:.1f} mm, head bone at {hd[2] * 1000:.1f} mm")
    report.guarded(st, "the avatar faces +Z (VRM 1.0)", faces_z)

    def handed():
        le, re_, _ = positions()
        return le[0] > 0 > re_[0], f"leftEye.x = {le[0] * 1000:.1f} mm, rightEye.x = {re_[0] * 1000:.1f} mm"
    report.guarded(st, "leftEye is on the character's left (+X)", handed)

    def gaze_origin():
        le, re_, hd = positions()
        want = [(le[i] + re_[i]) / 2 - hd[i] for i in range(3)]
        got = look["offsetFromHeadBone"]
        return (all(abs(a - b) < 0.001 for a, b in zip(got, want)),
                f"offsetFromHeadBone {[round(x, 4) for x in got]} vs eye midpoint "
                f"{[round(x, 4) for x in want]} (tolerance 1 mm)")
    report.guarded(st, "the gaze origin matches the eye bones", gaze_origin)

    def scene_set():
        got = sorted(n.get("name") for n in v.nodes if "mesh" in n)
        want = sorted(arkit52.ARCHETYPE_MESHES[archetype]["all"])
        return got == want, f"mesh nodes {got}"
    report.guarded(st, "the file carries only the avatar's meshes", scene_set)

    _check_evidence(report, v, custom, authored, evidence)
    check_springs1(report, glb, v, archetype)
    return v


def _names(glb):
    return [n.get("name") for n in glb.json.get("nodes", [])]


def _parent_of(glb):
    return {c: i for i, n in enumerate(glb.json.get("nodes", [])) for c in n.get("children", [])}


def collider_world(glb, collider):
    """World-space centre and radius of a VRM 1.0 sphere collider. Its offset is in the node's own frame."""
    m = glb.world_matrix(collider["node"])
    o = collider["shape"]["sphere"]["offset"]
    centre = tuple(sum(m[r][c] * o[c] for c in range(3)) + m[r][3] for r in range(3))
    return centre, collider["shape"]["sphere"]["radius"]


def check_springs1(report, glb, v, archetype):
    st = "contract"
    want = arkit52.ARCHETYPE_SPRINGS.get(archetype)
    if want is None:
        return
    j = glb.json
    sb = (j.get("extensions") or {}).get("VRMC_springBone")
    if not report.add(st, "the file declares VRMC_springBone", isinstance(sb, dict)
                      and "VRMC_springBone" in j.get("extensionsUsed", []),
                      f"extensionsUsed {j.get('extensionsUsed')}"):
        report.not_run(st, "spring-bone chains, centre and collider", "no VRMC_springBone extension to read")
        return
    names, parent = _names(glb), _parent_of(glb)
    springs = {s.get("name"): s for s in sb.get("springs", [])}
    report.add(st, "the spring chains are exactly the archetype's", sorted(springs) == sorted(want["chains"]),
               _set_diff(springs, want["chains"]))

    for chain, bones in want["chains"].items():
        def joints(chain=chain, bones=bones):
            nodes = [jt["node"] for jt in springs[chain]["joints"]]
            got = [names[n] for n in nodes]
            linked = all(parent.get(b) == a for a, b in zip(nodes, nodes[1:]))
            return got == list(bones) and linked, f"joints {got}" + ("" if linked else "; not parent-to-child")
        report.guarded(st, f"{chain}: joints are the expected bones, root first, each the child of the last", joints)

        def centre(chain=chain):
            c = springs[chain].get("center")
            return (c is not None and names[c] == want["center"],
                    f"center {names[c]!r}" if c is not None else "no center")
        report.guarded(st, f"{chain}: inertia is measured against {want['center']}", centre)

        def collides(chain=chain):
            groups = [sb["colliderGroups"][g] for g in springs[chain].get("colliderGroups", [])]
            got = [g.get("name") for g in groups]
            return want["collider_group"] in got, f"collider groups {got}"
        report.guarded(st, f"{chain}: collides with the {want['collider_group']} group", collides)

        def hit(chain=chain):
            radii = [jt.get("hitRadius", 0.0) for jt in springs[chain]["joints"]]
            return all(r > 0 for r in radii), f"hitRadius {[round(r, 4) for r in radii]}"
        report.guarded(st, f"{chain}: every joint has a hit radius", hit)

    def collider():
        group = next(g for g in sb["colliderGroups"] if g.get("name") == want["collider_group"])
        cols = [sb["colliders"][i] for i in group["colliders"]]
        ok = (len(cols) == 1 and names[cols[0]["node"]] == want["collider_bone"]
              and cols[0]["shape"]["sphere"]["radius"] > 0)
        return ok, f"{len(cols)} collider(s) on {[names[c['node']] for c in cols]}"
    report.guarded(st, f"the {want['collider_group']} group is one sphere on the {want['collider_bone']} bone",
                   collider)

    def frame():
        group = next(g for g in sb["colliderGroups"] if g.get("name") == want["collider_group"])
        centre, radius = collider_world(glb, sb["colliders"][group["colliders"][0]])
        bones = v.vrm["humanoid"]["humanBones"]
        far = {b: _dist(glb.world_position(bones[b]["node"]), centre) for b in ("leftEye", "rightEye")}
        return (all(d < radius for d in far.values()),
                f"sphere at {[round(c, 3) for c in centre]} r {radius * 1000:.0f} mm; eyes "
                f"{far['leftEye'] * 1000:.1f} / {far['rightEye'] * 1000:.1f} mm from its centre")
    report.guarded(st, "the head collider contains both eye bones (its offset is in the right frame)", frame)


def _dist(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def _check_evidence(report, v, custom, authored, evidence):
    st = "contract"
    if evidence is None:
        report.not_run(st, "file displacement agrees with the generator's own measurement",
                       "no evidence JSON beside the file")
        return
    figures = {}
    for row in evidence.get("checks", []):
        m = EVIDENCE_ROW.match(row.get("check", ""))
        mm = EVIDENCE_MM.match(row.get("detail", ""))
        if m and mm:
            figures[m.group(1)] = float(mm.group(1))
    missing = [n for n in authored if n not in figures]
    if missing:
        report.not_run(st, "file displacement agrees with the generator's own measurement",
                       f"the evidence JSON has no parseable figure for {len(missing)} shapes, e.g. {missing[:3]}")
        return

    def agree():
        off = []
        for name in authored:
            mesh_index, index, _ = v.resolve(custom[name]["morphTargetBinds"][0])
            mm = v.displacement_mm(mesh_index, index)
            if abs(mm - figures[name]) > 0.1:
                off.append(f"{name}: file {mm:.2f} vs generator {figures[name]:.1f}")
        return not off, "; ".join(off) or f"{len(authored)} shapes within 0.1 mm of the generator's figures"
    report.guarded(st, "file displacement agrees with the generator's own measurement", agree)


def check_vrm0(report, glb, archetype=None, glb1=None):
    st = "contract"
    j = glb.json
    vrm = (j.get("extensions") or {}).get("VRM")
    if not report.add(st, "the 0.x file declares the VRM extension", isinstance(vrm, dict),
                      f"specVersion {vrm.get('specVersion')!r}, exporter {vrm.get('exporterVersion')!r}"
                      if isinstance(vrm, dict) else f"extensions: {sorted(j.get('extensions') or {})}"):
        return
    groups = {g.get("presetName"): g for g in vrm.get("blendShapeMaster", {}).get("blendShapeGroups", [])}
    for attr in arkit52.PRESET_COMPOSITION:
        if attr not in VRM0_PRESET:
            continue

        def group_ok(attr=attr):
            g = groups[VRM0_PRESET[attr]]
            total = 0.0
            for bind in g["binds"]:
                prims = j["meshes"][bind["mesh"]]["primitives"]
                total += max(glb.max_vec3_length(p["targets"][bind["index"]]["POSITION"]) for p in prims) * 1000.0
            ok = len(g["binds"]) == len(arkit52.PRESET_COMPOSITION[attr]) and total > 0.0
            return ok, f"{len(g['binds'])} binds, {total:.1f} mm of target displacement behind them"
        report.guarded(st, f"0.x group {VRM0_PRESET[attr]} is bound and displaces", group_ok)

    def humanoid0():
        have = {b.get("bone") for b in vrm.get("humanoid", {}).get("humanBones", [])}
        missing = [b for b in VRM1_REQUIRED_BONES if b not in have]
        return not missing, f"{len(have)} bones" + (f"; missing {missing}" if missing else "")
    report.guarded(st, "the 0.x humanoid names the 15 required bones", humanoid0)

    # VRM 0.x faces -Z, a half turn from 1.0, so the character's left is at -X: the add-on's 0.x export of
    # the v1 rig has its eyes at z = -107 mm and leftEye.x = -68 mm.
    def frame0():
        at = {b["bone"]: glb.world_position(b["node"]) for b in vrm["humanoid"]["humanBones"]}
        le, re_, hd = at["leftEye"], at["rightEye"], at["head"]
        return (le[2] < hd[2] and re_[2] < hd[2] and le[0] < 0 < re_[0],
                f"eyes at z = {le[2] * 1000:.1f} / {re_[2] * 1000:.1f} mm, leftEye.x = {le[0] * 1000:.1f} mm")
    report.guarded(st, "the 0.x avatar faces -Z with leftEye at -X", frame0)
    check_springs0(report, glb, vrm, archetype, glb1)


def check_springs0(report, glb, vrm, archetype, glb1):
    st = "contract"
    want = arkit52.ARCHETYPE_SPRINGS.get(archetype)
    if want is None:
        return
    names = _names(glb)
    sa = vrm.get("secondaryAnimation") or {}
    groups = {g.get("comment"): g for g in sa.get("boneGroups", [])}
    if not report.add(st, "the 0.x bone groups are exactly the archetype's chains",
                      sorted(groups) == sorted(want["chains"]), _set_diff(groups, want["chains"])):
        return
    sb1 = ((glb1.json.get("extensions") or {}).get("VRMC_springBone") if glb1 else None) or {}
    springs1 = {s.get("name"): s for s in sb1.get("springs", [])}
    for chain, bones in want["chains"].items():
        def group(chain=chain, bones=bones):
            g = groups[chain]
            roots = [names[b] for b in g["bones"]]
            centre = names[g["center"]] if g.get("center", -1) >= 0 else None
            on = [names[sa["colliderGroups"][i]["node"]] for i in g.get("colliderGroups", [])]
            ok = roots == [bones[0]] and centre == want["center"] and on == [want["collider_bone"]]
            return ok, f"root {roots}, center {centre!r}, collider groups on {on}"
        report.guarded(st, f"0.x {chain}: root bone, centre and collider group", group)

        def same(chain=chain):
            g, j1 = groups[chain], springs1[chain]["joints"][0]
            pairs = {"stiffiness": "stiffness", "gravityPower": "gravityPower", "dragForce": "dragForce",
                     "hitRadius": "hitRadius"}
            off = {k0: (g[k0], j1[k1]) for k0, k1 in pairs.items() if abs(g[k0] - j1[k1]) > 1e-6}
            return not off, f"differs from the 1.0 file: {off}" if off else "equal to the 1.0 joints' parameters"
        if glb1 is not None:
            report.guarded(st, f"0.x {chain}: parameters equal the 1.0 file's", same)

    def collider0():
        cg = next(c for c in sa["colliderGroups"] if names[c["node"]] == want["collider_bone"])
        col = cg["colliders"][0]
        head = glb.world_position(cg["node"])
        # VRM 0.x offsets are in Unity's frame, which mirrors glTF's z; the 0.x file is the 1.0 file turned
        # half way round, so the same sphere sits at (-x, y, -z).
        centre0 = (head[0] + col["offset"]["x"], head[1] + col["offset"]["y"], head[2] - col["offset"]["z"])
        group1 = next(g for g in sb1["colliderGroups"] if g.get("name") == want["collider_group"])
        centre1, radius1 = collider_world(glb1, sb1["colliders"][group1["colliders"][0]])
        turned = (-centre1[0], centre1[1], -centre1[2])
        ok = _dist(centre0, turned) < 0.001 and abs(col["radius"] - radius1) < 0.001
        return ok, (f"0.x sphere at {[round(c, 3) for c in centre0]} r {col['radius']:.3f}; the 1.0 sphere "
                    f"turned half way round is at {[round(c, 3) for c in turned]} r {radius1:.3f}")
    if glb1 is not None:
        report.guarded(st, "the 0.x head collider is the 1.0 collider, turned half way round", collider0)


def _morph_mesh(v, archetype):
    want = arkit52.ARCHETYPE_MESHES[archetype]["morph_mesh"]
    for node in v.nodes:
        if node.get("name") == want and "mesh" in node:
            return node["mesh"]
    raise ValueError(f"no mesh node named {want!r}")


def _set_diff(got, want):
    got, want = set(got), set(want)
    if got == want:
        return f"{len(got)} names"
    return f"missing {sorted(want - got)}, unexpected {sorted(got - want)}"


# ---- command ---------------------------------------------------------------------------------------
def _sibling_json(path, suffix):
    stem = path.name.split(".")[0]
    candidate = path.with_name(f"{stem}{suffix}")
    if not candidate.is_file():
        return None
    try:
        return json.loads(candidate.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vrm", type=Path, help="VRM 1.0 file")
    ap.add_argument("--vrm0", type=Path, help="the derived VRM 0.x file")
    ap.add_argument("--archetype", help=f"one of {sorted(arkit52.ARCHETYPES)}; "
                                        "default: head_variant in <name>_manifest.json beside the file")
    ap.add_argument("--out", type=Path, help="report and contact sheet directory (default: beside the file)")
    ap.add_argument("--no-validator", action="store_true", help="switch the glTF-Validator stage off")
    ap.add_argument("--no-browser", action="store_true", help="switch the three-vrm / contact-sheet stage off")
    args = ap.parse_args(argv)

    problems = arkit52.check_contract()
    if problems:
        print("the contract table is inconsistent:\n  " + "\n  ".join(problems))
        return 2
    archetype = args.archetype or (_sibling_json(args.vrm, "_manifest.json") or {}).get("head_variant")
    if archetype not in arkit52.ARCHETYPES:
        print(f"archetype {archetype!r} is not known (give --archetype, or a manifest with head_variant); "
              f"known: {sorted(arkit52.ARCHETYPES)}")
        return 2
    out = args.out or args.vrm.parent / "vrm_gate"
    out.mkdir(parents=True, exist_ok=True)
    report = Report()
    files = [args.vrm] + ([args.vrm0] if args.vrm0 else [])

    print("stage: validator")
    if args.no_validator:
        report.stages["validator"] = "off"
        report.not_run("validator", "glTF-Validator", "switched off with --no-validator")
    else:
        import validator
        report.stages["validator"] = "ran" if validator.run(report, files) else "could-not-run"

    print("stage: contract")
    report.stages["contract"] = "ran"
    glb1 = check_container(report, args.vrm)
    v1 = check_vrm1(report, glb1, archetype, _sibling_json(args.vrm, "_evidence.json")) if glb1 else None
    if glb1 is None:
        report.not_run("contract", "VRM 1.0 contract checks", "the file could not be read")
    if args.vrm0:
        glb0 = check_container(report, args.vrm0)
        if glb0:
            check_vrm0(report, glb0, archetype, glb1)
        else:
            report.not_run("contract", "VRM 0.x checks", "the file could not be read")

    print("stage: consumer")
    if args.no_browser:
        report.stages["consumer"] = "off"
        report.not_run("consumer", "three-vrm and contact sheet", "switched off with --no-browser")
    elif v1 is None:
        report.stages["consumer"] = "could-not-run"
        report.not_run("consumer", "three-vrm and contact sheet", "the contract stage could not read the file")
    else:
        import browser
        report.stages["consumer"] = "ran" if browser.run(report, args.vrm, v1, archetype, out) else "could-not-run"

    summary = {"file": str(args.vrm), "vrm0": str(args.vrm0) if args.vrm0 else None, "archetype": archetype,
               "stages": report.stages, "passed": report.count(PASS), "failed": report.count(FAIL),
               "not_run": report.count(NOT_RUN), "ok": report.ok, "checks": report.rows}
    (out / "vrm_gate_report.json").write_text(json.dumps(summary, indent=1))
    stage_text = ", ".join(f"{k} {s}" for k, s in report.stages.items())
    print(f"\n{summary['passed']} passed, {summary['failed']} failed, {summary['not_run']} not run "
          f"— stages: {stage_text} — {'OK' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
