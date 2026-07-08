#!/usr/bin/env python3
"""Pack the WI 871 terrain library into three KTX2 texture arrays for Sounding (WI 872).

Arrays (10 layers each, canonical ALPHABETICAL set order — the runtime derives the same
order independently, no shared manifest):
  terrain_albedo.ktx2   sRGB   RGBA  (albedo, A=255)
  terrain_normal.ktx2   linear RGBA  (tangent-space normal, A=255)
  terrain_surface.ktx2  linear RGBA  (R=roughness, G=AO, B=height, A=255; metal dropped —
                                      terrain is dielectric; height comes from the banked
                                      harness maps, not the delivered 4-map sets)

Each array gets a full mip chain generated with WRAP-mode filtering (mip edges of tiling
textures must tile), UASTC encoding, and zstd supercompression, via the Khronos `ktx create`
tool (v5, owner-provisioned; `toktx` is its legacy interface). Outputs validated with
`ktx validate`.

Run: python pack_terrain_ktx2.py [out_dir]   (default out: outputs/ktx2/)
Then copy the three .ktx2 into the Sounding repo's crates/app/assets/materials/.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

KTX = "/opt/KTX-Software/build/Release/ktx"  # absolute: PATH may lack it in fresh shells
SETS = sorted([
    "basalt", "forest_floor", "grass", "mud", "regolith_coarse",
    "regolith_fine", "rock", "sand", "snow", "steppe",
])
SIZE = 1024


def stage(lib: Path, work: Path) -> dict:
    """Write per-layer RGBA staging PNGs; returns {array_name: [layer paths in order]}."""
    staged = {"albedo": [], "normal": [], "surface": []}
    for name in SETS:
        d = lib / name
        albedo = Image.open(d / f"{name}_albedo.png").convert("RGBA")
        normal = Image.open(d / f"{name}_normal.png").convert("RGBA")
        # metallic_roughness: G=roughness (Bevy/glTF packing); occlusion: R=AO; height: L.
        rough = Image.open(d / f"{name}_metallic_roughness.png").convert("RGB").split()[1]
        ao = Image.open(d / f"{name}_occlusion.png").convert("RGB").split()[0]
        height = Image.open(d / f"{name}_height.png").convert("L")
        alpha = Image.new("L", (SIZE, SIZE), 255)
        surface = Image.merge("RGBA", (rough, ao, height, alpha))
        for arr, img in (("albedo", albedo), ("normal", normal), ("surface", surface)):
            assert img.size == (SIZE, SIZE), (name, arr, img.size)
            p = work / f"{arr}_{name}.png"
            img.save(p)
            staged[arr].append(p)
    return staged


def create(array: str, layers: list, out_dir: Path, srgb: bool) -> Path:
    out = out_dir / f"terrain_{array}.ktx2"
    fmt = "R8G8B8A8_SRGB" if srgb else "R8G8B8A8_UNORM"
    cmd = [KTX, "create", "--format", fmt, "--layers", str(len(layers)),
           "--generate-mipmap", "--mipmap-wrap", "wrap",
           "--encode", "uastc", "--zstd", "19",
           *[str(p) for p in layers], str(out)]
    # Be explicit about the input transfer function: data maps (normals, rough/AO/height)
    # are raw linear values — without --assign-tf the tool assumes sRGB PNGs and applies a
    # lossy sRGB->linear value conversion. Albedo really is sRGB (matches --format, no-op).
    cmd[2:2] = ["--assign-tf", "srgb" if srgb else "linear"]
    subprocess.run(cmd, check=True)
    subprocess.run([KTX, "validate", str(out)], check=True)
    info = subprocess.run([KTX, "info", str(out)], check=True, capture_output=True, text=True)
    head = [ln for ln in info.stdout.splitlines()
            if any(k in ln for k in ("vkFormat", "layerCount", "levelCount", "supercompression"))]
    print(f"{out.name}: {out.stat().st_size // (1024 * 1024)} MiB")
    for ln in head:
        print(f"  {ln.strip()}")
    return out


def main() -> None:
    here = Path(__file__).parent
    lib = here / "outputs" / "library"
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "outputs" / "ktx2"
    work = out_dir / "staging"
    work.mkdir(parents=True, exist_ok=True)
    staged = stage(lib, work)
    print(f"layer order: {SETS}")
    create("albedo", staged["albedo"], out_dir, srgb=True)
    create("normal", staged["normal"], out_dir, srgb=False)
    create("surface", staged["surface"], out_dir, srgb=False)


if __name__ == "__main__":
    main()
