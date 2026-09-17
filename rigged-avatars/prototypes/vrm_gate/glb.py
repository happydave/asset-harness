"""Minimal GLB reader for the VRM gate: chunks, accessors (dense and sparse), node world transforms.

Stdlib only, so it runs under plain `python3` on any host and inside Blender's Python alike.
"""
import json
import math
import struct
from array import array

GLB_MAGIC = b"glTF"
CHUNK_JSON = b"JSON"
CHUNK_BIN = b"BIN\x00"

# componentType -> (array typecode, byte size)
_COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GlbError(Exception):
    """The container or an accessor is malformed; the message says where."""


class Glb:
    def __init__(self, data):
        if len(data) < 12:
            raise GlbError(f"{len(data)} bytes is shorter than a GLB header")
        magic, version, length = struct.unpack_from("<4sII", data, 0)
        if magic != GLB_MAGIC:
            raise GlbError(f"magic is {magic!r}, not {GLB_MAGIC!r}")
        if version != 2:
            raise GlbError(f"GLB version {version}, expected 2")
        if length != len(data):
            raise GlbError(f"header declares {length} bytes, file has {len(data)}")
        self.chunks = []
        offset = 12
        while offset < length:
            if offset + 8 > length:
                raise GlbError(f"chunk header at {offset} runs past the end of the file")
            size, kind = struct.unpack_from("<I4s", data, offset)
            start = offset + 8
            if start + size > length:
                raise GlbError(f"{kind!r} chunk at {offset} declares {size} bytes, past the end of the file")
            self.chunks.append((kind, start, size))
            offset = start + size
        json_chunks = [c for c in self.chunks if c[0] == CHUNK_JSON]
        if len(json_chunks) != 1 or self.chunks[0][0] != CHUNK_JSON:
            raise GlbError(f"expected one leading JSON chunk, found kinds {[c[0] for c in self.chunks]}")
        _, start, size = json_chunks[0]
        try:
            self.json = json.loads(data[start:start + size].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise GlbError(f"JSON chunk does not parse: {e}") from e
        bins = [c for c in self.chunks if c[0] == CHUNK_BIN]
        self.bin = memoryview(data)[bins[0][1]:bins[0][1] + bins[0][2]] if bins else None
        self._world = {}

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    # ---- accessors ----------------------------------------------------------------------------
    def _view_bytes(self, view_index):
        views = self.json.get("bufferViews", [])
        if not 0 <= view_index < len(views):
            raise GlbError(f"bufferView {view_index} does not exist")
        view = views[view_index]
        if view.get("buffer", 0) != 0 or self.bin is None:
            raise GlbError(f"bufferView {view_index} is not in the embedded BIN chunk")
        start = view.get("byteOffset", 0)
        end = start + view["byteLength"]
        if end > len(self.bin):
            raise GlbError(f"bufferView {view_index} ends at {end}, BIN chunk has {len(self.bin)} bytes")
        return self.bin[start:end], view.get("byteStride")

    def _read(self, view_index, byte_offset, component_type, width, count):
        """`count` elements of `width` components as one flat array."""
        if component_type not in _COMPONENT:
            raise GlbError(f"componentType {component_type} is not a glTF component type")
        code, size = _COMPONENT[component_type]
        raw, stride = self._view_bytes(view_index)
        element = size * width
        stride = stride or element
        need = byte_offset + (stride * (count - 1) + element if count else 0)
        if need > len(raw):
            raise GlbError(f"accessor needs {need} bytes of bufferView {view_index}, which has {len(raw)}")
        out = array(code)
        if stride == element:
            out.frombytes(raw[byte_offset:byte_offset + element * count])
        else:
            for i in range(count):
                at = byte_offset + i * stride
                out.frombytes(raw[at:at + element])
        return out

    def accessor(self, index):
        """The accessor's values as a flat array of count * width components, sparse values applied."""
        accessors = self.json.get("accessors", [])
        if not 0 <= index < len(accessors):
            raise GlbError(f"accessor {index} does not exist")
        acc = accessors[index]
        if acc.get("type") not in _WIDTH:
            raise GlbError(f"accessor {index} has type {acc.get('type')!r}")
        width, count = _WIDTH[acc["type"]], acc["count"]
        if "bufferView" in acc:
            values = self._read(acc["bufferView"], acc.get("byteOffset", 0), acc["componentType"], width, count)
        else:
            code, _ = _COMPONENT.get(acc["componentType"], (None, None))
            if code is None:
                raise GlbError(f"accessor {index} has componentType {acc['componentType']}")
            values = array(code, [0]) * (count * width)
        sparse = acc.get("sparse")
        if sparse:
            n = sparse["count"]
            idx = sparse["indices"]
            where = self._read(idx["bufferView"], idx.get("byteOffset", 0), idx["componentType"], 1, n)
            val = sparse["values"]
            what = self._read(val["bufferView"], val.get("byteOffset", 0), acc["componentType"], width, n)
            for k, target in enumerate(where):
                if target >= count:
                    raise GlbError(f"accessor {index} sparse index {target} is past its count {count}")
                values[target * width:(target + 1) * width] = what[k * width:(k + 1) * width]
        return values

    def max_vec3_length(self, index):
        """Largest Euclidean length among a VEC3 accessor's elements."""
        acc = self.json["accessors"][index] if 0 <= index < len(self.json.get("accessors", [])) else None
        if acc is None or acc.get("type") != "VEC3":
            raise GlbError(f"accessor {index} is not a VEC3")
        v = self.accessor(index)
        best = 0.0
        for i in range(0, len(v), 3):
            sq = v[i] * v[i] + v[i + 1] * v[i + 1] + v[i + 2] * v[i + 2]
            if sq > best:
                best = sq
        return math.sqrt(best)

    # ---- nodes --------------------------------------------------------------------------------
    def _parents(self):
        parents = {}
        for i, node in enumerate(self.json.get("nodes", [])):
            for child in node.get("children", []):
                parents[child] = i
        return parents

    def world_matrix(self, node_index):
        """Row-major 4x4 world matrix of a node, composed up its parent chain."""
        if node_index in self._world:
            return self._world[node_index]
        nodes = self.json.get("nodes", [])
        if not 0 <= node_index < len(nodes):
            raise GlbError(f"node {node_index} does not exist")
        if not hasattr(self, "_parent_of"):
            self._parent_of = self._parents()
        local = _local_matrix(nodes[node_index])
        parent = self._parent_of.get(node_index)
        world = local if parent is None else _matmul(self.world_matrix(parent), local)
        self._world[node_index] = world
        return world

    def world_position(self, node_index):
        m = self.world_matrix(node_index)
        return (m[0][3], m[1][3], m[2][3])


def _local_matrix(node):
    if "matrix" in node:
        c = node["matrix"]  # glTF stores column-major
        return [[c[0], c[4], c[8], c[12]], [c[1], c[5], c[9], c[13]],
                [c[2], c[6], c[10], c[14]], [c[3], c[7], c[11], c[15]]]
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0.0, 0.0, 0.0, 1.0]]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
