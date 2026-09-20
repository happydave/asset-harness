#!/usr/bin/env python3
"""WI 1616 — derive podman flags from a CDI spec podman 4.9.3 cannot parse.

podman 4.9.3's CDI library rejects the nvidia-ctk 0.7.0 spec on the unknown
field `additionalGids`, and it ignores `cdi_spec_dirs`, so a user-level
override is impossible. But the spec is readable, and everything in it except
the hooks is expressible as plain podman flags. The hooks only build an
ld.so cache and symlinks; LD_LIBRARY_PATH substitutes for the first, and the
second is not needed for nvidia-smi or for torch's CUDA runtime.

Safe on this host specifically because /dev/nvidia* are mode 666, so the
spec's additionalGids (44, 992) buy nothing.
"""
import sys, yaml

spec = yaml.safe_load(open("/etc/cdi/nvidia.yaml"))
device = sys.argv[1] if len(sys.argv) > 1 else "all"

edits = [spec.get("containerEdits", {})]
for d in spec.get("devices", []):
    if d.get("name") == device:
        edits.append(d.get("containerEdits", {}))

args, libdirs = [], set()
seen_dev, seen_mnt = set(), set()
for e in edits:
    for dn in e.get("deviceNodes", []) or []:
        p = dn.get("path")
        if p and p not in seen_dev:
            seen_dev.add(p); args += ["--device", "%s:%s:rwm" % (p, p)]
    for m in e.get("mounts", []) or []:
        hp, cp = m.get("hostPath"), m.get("containerPath")
        if not hp or (hp, cp) in seen_mnt:
            continue
        seen_mnt.add((hp, cp))
        opts = [o for o in (m.get("options") or []) if o in ("ro", "rw", "nosuid", "nodev", "noexec")]
        args += ["-v", "%s:%s:%s" % (hp, cp, ",".join(opts) if opts else "ro")]
        if cp.endswith(".so") or ".so." in cp:
            libdirs.add(cp.rsplit("/", 1)[0])
    for kv in e.get("env", []) or []:
        if kv.startswith("NVIDIA_CTK_"):
            continue
        args += ["-e", kv]

if libdirs:
    args += ["-e", "LD_LIBRARY_PATH=" + ":".join(sorted(libdirs))]
print(" ".join(args))
