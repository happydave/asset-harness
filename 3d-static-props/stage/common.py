"""Shared helpers: frames, canonical JSON, hashes, safe names, the dense source in the normalised frame."""
import hashlib
import json
import os
import re

import numpy as np
import trimesh

# glTF (y up) to the stage's frame (z up), as Blender's glTF importer brings a glb in: x, -z, y
TO_Z_UP = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
TO_Y_UP = TO_Z_UP.T

# generators the stage knows the up axis of: the lane record's `arm`
GENERATORS = {"trellis2": "source"}

NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def safe_name(name):
    """A name that stays inside the output directory: no separators, no leading dot, no `..`."""
    return bool(NAME.match(name)) and ".." not in name and not name.startswith(".")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=str)


def load_zup(path, matrix=None):
    """A glb as one mesh in the z-up frame, then the normaliser's matrix when given."""
    mesh = trimesh.load(path, force="mesh", process=False)
    mesh.apply_transform(TO_Z_UP)
    if matrix is not None:
        mesh.apply_transform(np.asarray(matrix, float))
    return mesh


def welded(mesh):
    """Positions alone: UV seams and flat normals split vertices, which would count every UV island as
    a piece and no mesh as closed."""
    m = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False)
    m.merge_vertices(merge_tex=True, merge_norm=True)
    return m


def export_yup(mesh, path):
    """Write a z-up mesh as a glb, which the glTF importer turns back to z up."""
    m = mesh.copy()
    m.apply_transform(TO_Y_UP)
    m.export(path)


def tool_paths():
    """Blender and glTF-Validator: the environment's, else the run folder's defaults on ai2."""
    here = os.path.dirname(os.path.abspath(__file__))
    return {
        "blender": os.environ.get("STAGE_BLENDER", os.path.expanduser("~/blender-4.2/blender")),
        "validator": os.environ.get("STAGE_VALIDATOR", os.path.join(here, "bin", "gltf_validator")),
        "threads": os.environ.get("STAGE_THREADS", "12"),
    }
