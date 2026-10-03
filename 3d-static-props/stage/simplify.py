"""meshoptimizer's simplifiers, called through its bundled library: the 0.2.30a0 binding passes Python
floats where the library wants C floats and fails, so the functions are called directly."""
import ctypes as C

import numpy as np
from meshoptimizer.simplifier import lib

F, U = C.POINTER(C.c_float), C.POINTER(C.c_uint)


def simplify(vertices, faces, target_tris, max_error=1.0, uv=None):
    """Faces simplified toward target_tris: the topology-keeping simplifier (with UVs when given), and the
    sloppy one when the first stops more than a quarter above the target and the sloppy gets nearer.
    Returns (faces, how, relative_error)."""
    pos = np.ascontiguousarray(vertices, dtype=np.float32)
    idx = np.ascontiguousarray(np.asarray(faces).reshape(-1), dtype=np.uint32)
    dst = np.zeros_like(idx)
    err = C.c_float(0)
    target = C.c_size_t(int(target_tris) * 3)
    if uv is not None:
        tex = np.ascontiguousarray(uv, dtype=np.float32)
        w = np.array([0.5, 0.5], dtype=np.float32)
        n = lib.meshopt_simplifyWithAttributes(dst.ctypes.data_as(U), idx.ctypes.data_as(U), C.c_size_t(len(idx)),
                                               pos.ctypes.data_as(F), C.c_size_t(len(pos)), C.c_size_t(12),
                                               tex.ctypes.data_as(F), C.c_size_t(8), w.ctypes.data_as(F), C.c_size_t(2),
                                               C.POINTER(C.c_ubyte)(), target, C.c_float(max_error),
                                               C.c_uint(0), C.byref(err))
        how = "attributes"
    else:
        n = lib.meshopt_simplify(dst.ctypes.data_as(U), idx.ctypes.data_as(U), C.c_size_t(len(idx)),
                                 pos.ctypes.data_as(F), C.c_size_t(len(pos)), C.c_size_t(12),
                                 target, C.c_float(max_error), C.c_uint(0), C.byref(err))
        how = "topology"
    if n > target_tris * 3 * 1.25:
        alt = np.zeros_like(idx)
        alt_err = C.c_float(0)
        m = lib.meshopt_simplifySloppy(alt.ctypes.data_as(U), idx.ctypes.data_as(U), C.c_size_t(len(idx)),
                                       pos.ctypes.data_as(F), C.c_size_t(len(pos)), C.c_size_t(12),
                                       target, C.c_float(max_error), C.byref(alt_err))
        stopped = n // 3
        how = f"{how} (stopped at {stopped})"
        if 0 < m < n:  # the sloppy simplifier ignores seams and topology: kept only when nearer the target
            dst, n, err, how = alt, m, alt_err, f"sloppy ({how})"
    return dst[:n].reshape(-1, 3), how, float(err.value)
