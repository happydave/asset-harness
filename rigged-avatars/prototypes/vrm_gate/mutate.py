#!/usr/bin/env python3
"""Write a deliberately broken copy of a VRM 1.0 file, one named defect at a time.

    python3 mutate.py IN.vrm OUT.vrm MUTATION

The gate's negative controls: each mutation is a defect a named check exists to catch. The input is
never written to, and each mutation re-reads its output and confirms the defect landed before
reporting success — a control whose mutation silently failed to apply forges a passing gate.
"""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from glb import Glb, GLB_MAGIC, CHUNK_JSON, CHUNK_BIN  # noqa: E402

FACE = "face"
AUTHORED_A, AUTHORED_B = "jawOpen", "mouthPucker"
STUB = "tongueOut"


class Draft:
    def __init__(self, path):
        self.path = path
        glb = Glb.load(path)
        self.json = glb.json
        self.bin = bytearray(glb.bin)

    @property
    def vrm(self):
        return self.json["extensions"]["VRMC_vrm"]

    @property
    def custom(self):
        return self.vrm["expressions"]["custom"]

    def face_node(self):
        return next(i for i, n in enumerate(self.json["nodes"]) if n.get("name") == FACE and "mesh" in n)

    def face_mesh(self):
        return self.json["meshes"][self.json["nodes"][self.face_node()]["mesh"]]

    def target_index(self, name):
        return self.face_mesh()["extras"]["targetNames"].index(name)

    def append_bin(self, payload):
        """Append bytes to the buffer as a new bufferView; returns its index."""
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin += payload
        self.json["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": len(payload)})
        return len(self.json["bufferViews"]) - 1

    def add_flat_target(self, name, poke=None):
        """A new morph target with all-zero deltas on every primitive, bound to nothing yet. With `poke`,
        vertex 0 of the first primitive moves by that vector, carried by a sparse accessor."""
        mesh = self.face_mesh()
        for p, prim in enumerate(mesh["primitives"]):
            count = self.json["accessors"][prim["attributes"]["POSITION"]]["count"]
            acc = {"componentType": 5126, "count": count, "type": "VEC3",
                   "min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
            if poke and p == 0:
                indices = self.append_bin(struct.pack("<I", 0))
                values = self.append_bin(struct.pack("<3f", *poke))
                acc["sparse"] = {"count": 1,
                                 "indices": {"bufferView": indices, "componentType": 5125},
                                 "values": {"bufferView": values}}
                acc["min"] = [min(0.0, c) for c in poke]
                acc["max"] = [max(0.0, c) for c in poke]
            self.json["accessors"].append(acc)
            prim["targets"].append({"POSITION": len(self.json["accessors"]) - 1})
        mesh["extras"]["targetNames"].append(name)
        if "weights" in mesh:
            mesh["weights"].append(0.0)
        return len(mesh["extras"]["targetNames"]) - 1

    def write(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.json["buffers"][0]["byteLength"] = len(self.bin)
        text = json.dumps(self.json, separators=(",", ":")).encode("utf-8")
        text += b" " * (-len(text) % 4)
        total = 12 + 8 + len(text) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", GLB_MAGIC, 2, total))
            f.write(struct.pack("<I4s", len(text), CHUNK_JSON) + text)
            f.write(struct.pack("<I4s", len(self.bin), CHUNK_BIN) + bytes(self.bin))


# Each mutation edits the draft and returns a predicate over the re-read output that is true only if the
# defect is really in the written file.
def rename_key(d):
    names = d.face_mesh()["extras"]["targetNames"]
    i = names.index(AUTHORED_A)
    names[i] = AUTHORED_A + "Renamed"
    return lambda o: o.face_mesh()["extras"]["targetNames"][i] == AUTHORED_A + "Renamed"


def drop_bind(d):
    del d.custom[AUTHORED_A]["morphTargetBinds"]
    return lambda o: "morphTargetBinds" not in o.custom[AUTHORED_A]


def stub_bind(d):
    bind = {"node": d.face_node(), "index": d.target_index(AUTHORED_A), "weight": 1.0}
    d.custom[STUB]["morphTargetBinds"] = [bind]
    return lambda o: o.custom[STUB]["morphTargetBinds"] == [bind]


def stub_flat(d):
    index = d.add_flat_target(STUB)
    d.custom[STUB]["morphTargetBinds"] = [{"node": d.face_node(), "index": index, "weight": 1.0}]
    return lambda o: (o.custom[STUB]["morphTargetBinds"][0]["index"] == index
                      and _target_max(o, index) == 0.0)


def stub_nonzero(d):
    index = d.add_flat_target(STUB, poke=(0.0, 0.004, 0.0))
    d.custom[STUB]["morphTargetBinds"] = [{"node": d.face_node(), "index": index, "weight": 1.0}]
    return lambda o: abs(_target_max(o, index) - 0.004) < 1e-7


def reindex(d):
    a, b = d.custom[AUTHORED_A]["morphTargetBinds"][0], d.custom[AUTHORED_B]["morphTargetBinds"][0]
    a["index"], b["index"] = b["index"], a["index"]
    want = (a["index"], b["index"])
    return lambda o: (o.custom[AUTHORED_A]["morphTargetBinds"][0]["index"],
                      o.custom[AUTHORED_B]["morphTargetBinds"][0]["index"]) == want


def flatten(d):
    index = d.target_index(AUTHORED_A)
    # Normals too: a shape that stopped deforming exports flat normal deltas, and leaving them would
    # still shade the face differently, which is not the defect being modelled.
    for prim in d.face_mesh()["primitives"]:
        for attribute in ("POSITION", "NORMAL"):
            if attribute not in prim["targets"][index]:
                continue
            acc = d.json["accessors"][prim["targets"][index][attribute]]
            view = d.json["bufferViews"][acc["bufferView"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            d.bin[start:start + acc["count"] * 12] = bytes(acc["count"] * 12)
            if "min" in acc:
                acc["min"], acc["max"] = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    return lambda o: _target_max(o, index) == 0.0


def case_drift(d):
    d.custom["eyeblinkleft"] = d.custom.pop("eyeBlinkLeft")
    return lambda o: "eyeblinkleft" in o.custom and "eyeBlinkLeft" not in o.custom


def transpose_gaze(d):
    x, y, z = d.vrm["lookAt"]["offsetFromHeadBone"]
    d.vrm["lookAt"]["offsetFromHeadBone"] = [x, z, y]
    return lambda o: o.vrm["lookAt"]["offsetFromHeadBone"] == [x, z, y] and y != z


def wrong_weight(d):
    bind = d.vrm["expressions"]["preset"]["ih"]["morphTargetBinds"][0]
    bind["weight"] = round(bind["weight"] + 0.2, 4)
    want = bind["weight"]
    return lambda o: o.vrm["expressions"]["preset"]["ih"]["morphTargetBinds"][0]["weight"] == want


def bad_max(d):
    prim = d.face_mesh()["primitives"][0]
    acc = d.json["accessors"][prim["targets"][d.target_index(AUTHORED_A)]["POSITION"]]
    acc["max"] = [acc["max"][0] + 1.0, acc["max"][1], acc["max"][2]]
    want = list(acc["max"])
    return lambda o: o.json["accessors"][prim["targets"][o.target_index(AUTHORED_A)]["POSITION"]]["max"] == want


def _springs(d):
    return d.json["extensions"]["VRMC_springBone"]["springs"]


def drop_center(d):
    for spring in _springs(d):
        spring.pop("center", None)
    return lambda o: all("center" not in spring for spring in _springs(o))


def drop_collider_group(d):
    for spring in _springs(d):
        spring.pop("colliderGroups", None)
    return lambda o: all("colliderGroups" not in spring for spring in _springs(o))


def center_head(d):
    head = next(i for i, n in enumerate(d.json["nodes"]) if n.get("name") == "head")
    for spring in _springs(d):
        spring["center"] = head
    return lambda o: all(spring.get("center") == head for spring in _springs(o))


def collider_transposed(d):
    sphere = d.json["extensions"]["VRMC_springBone"]["colliders"][0]["shape"]["sphere"]
    x, y, z = sphere["offset"]
    sphere["offset"] = [x, z, y]
    return lambda o: (o.json["extensions"]["VRMC_springBone"]["colliders"][0]["shape"]["sphere"]["offset"]
                      == [x, z, y] and y != z)


def joint_order(d):
    joints = _springs(d)[0]["joints"]
    joints[0], joints[1] = joints[1], joints[0]
    want = [j["node"] for j in joints]
    return lambda o: [j["node"] for j in _springs(o)[0]["joints"]] == want


def _target_max(draft, index):
    glb = Glb.load(draft.path)
    return max(glb.max_vec3_length(p["targets"][index]["POSITION"]) for p in draft.face_mesh()["primitives"])


MUTATIONS = {
    "rename-key": rename_key, "drop-bind": drop_bind, "stub-bind": stub_bind, "stub-flat": stub_flat,
    "stub-nonzero": stub_nonzero, "reindex": reindex, "flatten": flatten, "case-drift": case_drift,
    "transpose-gaze": transpose_gaze, "wrong-weight": wrong_weight, "bad-max": bad_max,
    "drop-center": drop_center, "drop-collider-group": drop_collider_group, "joint-order": joint_order,
    "center-head": center_head, "collider-transposed": collider_transposed,
}


def would_overwrite_input(src, dst):
    """True when writing `dst` would destroy `src`: the same file by path, by symlink, or by hard link."""
    src, dst = Path(src).resolve(), Path(dst).resolve()
    return src == dst or (dst.exists() and src.exists() and src.samefile(dst))


def mutate(src, dst, name):
    if would_overwrite_input(src, dst):
        raise SystemExit("refusing to write over the input")
    src, dst = Path(src).resolve(), Path(dst).resolve()
    if name not in MUTATIONS:
        raise SystemExit(f"unknown mutation {name!r}; known: {sorted(MUTATIONS)}")
    draft = Draft(src)
    landed = MUTATIONS[name](draft)
    draft.write(dst)
    reread = Draft(dst)
    if not landed(reread):
        raise SystemExit(f"mutation {name!r} did not land in {dst}")
    return dst


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    print(mutate(*sys.argv[1:]))
