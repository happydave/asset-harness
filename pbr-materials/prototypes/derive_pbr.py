#!/usr/bin/env python3
"""Derive a Bevy-ready PBR map set from a single albedo — deterministic, PIL-only, fully clean.

From an albedo we produce: a seamless albedo, a tangent-space normal map (Sobel-style from a
height proxy), roughness, metallic (flat per material), a packed metallic-roughness texture
(Bevy: R=0, G=roughness, B=metallic), an AO/occlusion map (cavity), and a height map. Quality is
an approximation (single-image derivation) — good for mid/background surfaces.

Usage: python derive_pbr.py albedo.png out_dir name --metal 0.85 --rough-base 150
"""
import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

L = "L"


def flatten_luminance(img: Image.Image, radius: int = 96) -> Image.Image:
    """Delight: remove low-frequency luminance variation (a baked highlight sweep / vignette /
    gradient) while preserving high-frequency surface detail and each channel's mean colour.

    For each channel: out = channel - blur(luma) + channel_mean (clamped). The large-scale lighting
    gradient cancels; the fine grain/scratches survive. Pure PIL, deterministic — for flat metal
    albedos the txt2img model tends to render as a lit surface."""
    low = img.convert(L).filter(ImageFilter.GaussianBlur(radius))
    out = []
    for ch in img.convert("RGB").split():
        m = int(round(ImageStat.Stat(ch).mean[0]))
        out.append(ImageChops.subtract(ch, low, 1.0, m))  # (ch - low) + m, clamped to [0,255]
    return Image.merge("RGB", out)


def make_seamless(img: Image.Image, margin: int = 0) -> Image.Image:
    """Border cross-fade: blend the right margin toward the left edge (and bottom toward top).

    Only a thin border band is modified — the interior stays pristine — and the blended band lands
    on the tile boundary where a short transition is expected. Avoids the visible centre cross of a
    half-offset heal. Pure PIL (a linear ramp mask + composite)."""
    w, h = img.size
    m = margin or w // 8
    out = img.copy()
    # horizontal: right margin ramps into the left-edge content
    rh = Image.new(L, (m, 1)); rh.putdata([int(255 * i / (m - 1)) for i in range(m)])
    rh = rh.resize((m, h))
    out.paste(Image.composite(out.crop((0, 0, m, h)), out.crop((w - m, 0, w, h)), rh), (w - m, 0))
    # vertical: bottom margin ramps into the top-edge content
    rv = Image.new(L, (1, m)); rv.putdata([int(255 * i / (m - 1)) for i in range(m)])
    rv = rv.resize((w, m))
    out.paste(Image.composite(out.crop((0, 0, w, m)), out.crop((0, h - m, w, h)), rv), (0, h - m))
    return out


def height_proxy(albedo: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(albedo.convert(L)).filter(ImageFilter.GaussianBlur(1))


def normal_map(height: Image.Image, strength: float = 4.0, flip_g: bool = False) -> Image.Image:
    """Sobel-style tangent normal from a height proxy, using 1px wrapped shifts (stays tileable)."""
    scale = max(0.4, 6.0 / strength)
    hl, hr = ImageChops.offset(height, -1, 0), ImageChops.offset(height, 1, 0)
    hu, hd = ImageChops.offset(height, 0, -1), ImageChops.offset(height, 0, 1)
    nx = ImageChops.subtract(hl, hr, scale, 128)            # +X to the right
    ny = ImageChops.subtract(hd, hu, scale, 128)            # +Y up (OpenGL); flip for DirectX
    if flip_g:
        ny = ImageChops.invert(ny)
    nb = Image.new(L, height.size, 255)
    return Image.merge("RGB", (nx, ny, nb))


def roughness_map(albedo: Image.Image, base: int = 160, contrast: float = 0.6) -> Image.Image:
    g = ImageOps.autocontrast(albedo.convert(L))
    return g.point(lambda v: int(max(0, min(255, base + (v - 128) * contrast))))


def ao_map(height: Image.Image) -> Image.Image:
    blur = height.filter(ImageFilter.GaussianBlur(10))
    cav = ImageChops.subtract(blur, height, 1.0, 0).point(lambda v: min(255, int(v * 2.2)))
    return ImageChops.invert(cav)                            # dark in crevices, white elsewhere


def derive(albedo_path: Path, out_dir: Path, name: str,
           metal: float = 0.0, rough_base: int = 160, normal_strength: float = 4.0,
           flip_g: bool = False, flatten: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Image.open(albedo_path).convert("RGB")
    if flatten:  # delight a baked lighting gradient before tiling (flat-metal albedos, WI 624)
        src = flatten_luminance(src)
    albedo = make_seamless(src)
    height = height_proxy(albedo)
    normal = normal_map(height, normal_strength, flip_g)
    rough = roughness_map(albedo, rough_base)
    metallic = Image.new(L, albedo.size, int(metal * 255))
    zeros = Image.new(L, albedo.size, 0)
    metal_rough = Image.merge("RGB", (zeros, rough, metallic))   # Bevy: G=rough, B=metal
    ao = ao_map(height)

    paths = {
        "albedo": out_dir / f"{name}_albedo.png",
        "normal": out_dir / f"{name}_normal.png",
        "metallic_roughness": out_dir / f"{name}_metallic_roughness.png",
        "occlusion": out_dir / f"{name}_occlusion.png",
        "height": out_dir / f"{name}_height.png",
    }
    albedo.save(paths["albedo"])
    normal.save(paths["normal"])
    metal_rough.save(paths["metallic_roughness"])
    ao.save(paths["occlusion"])
    height.save(paths["height"])

    # 3x3 tiled preview to eyeball seamlessness
    w, h = albedo.size
    prev = Image.new("RGB", (w * 3, h * 3))
    for i in range(3):
        for j in range(3):
            prev.paste(albedo, (i * w, j * h))
    prev.resize((w, h), Image.LANCZOS).save(out_dir / f"{name}_tiled_preview.png")
    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("albedo")
    ap.add_argument("out_dir")
    ap.add_argument("name")
    ap.add_argument("--metal", type=float, default=0.0)
    ap.add_argument("--rough-base", type=int, default=160)
    ap.add_argument("--normal-strength", type=float, default=3.0)
    ap.add_argument("--flip-g", action="store_true")
    ap.add_argument("--flatten", action="store_true")
    args = ap.parse_args()
    paths = derive(Path(args.albedo), Path(args.out_dir), args.name,
                   args.metal, args.rough_base, args.normal_strength, args.flip_g, args.flatten)
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
