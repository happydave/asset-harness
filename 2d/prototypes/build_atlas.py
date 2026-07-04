#!/usr/bin/env python3
"""Downstream post-processing: trim -> downscale -> pack into a Phaser texture atlas.

Takes the RGBA sprites produced by the generator and turns them into engine-ready output:
  1. trim each sprite to its alpha bounding box (drop empty margins; sub-threshold matting
     specks are ignored via --alpha-threshold so speckly mattes still trim tight),
  2. downscale so the largest dimension == --max-dim (game resolution),
  3. shelf-pack the frames into a single atlas PNG,
  4. emit a Phaser-compatible JSON-Hash atlas descriptor.

Reads a fleet_manifest.json (name -> rgba filename) or an explicit list of files.
Stdlib + PIL only.
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image

PAD = 2


def trim_and_fit(path: Path, max_dim: int, alpha_threshold: int = 0) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    alpha = im.getchannel("A")
    if alpha_threshold > 0:
        # Ignore sub-threshold matting specks when finding the crop box: BiRefNet sometimes
        # leaves faint alpha (< a few /255) across otherwise-transparent borders, which makes a
        # naive getbbox() return the full frame. The retained crop is still taken from the
        # original image, so subject pixels and anti-aliased edges are untouched.
        alpha = alpha.point(lambda a: a if a >= alpha_threshold else 0)
    bbox = alpha.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    scale = max_dim / max(w, h)
    if scale < 1.0:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return im


def shelf_pack(sizes, atlas_w):
    """Return (placements [(x,y)], atlas_w, atlas_h). sizes: list of (w,h)."""
    x = y = shelf_h = 0
    placements = []
    for w, h in sizes:
        if x + w + PAD > atlas_w and x > 0:      # wrap to next shelf
            x = 0
            y += shelf_h + PAD
            shelf_h = 0
        placements.append((x, y))
        x += w + PAD
        shelf_h = max(shelf_h, h)
    atlas_h = y + shelf_h
    return placements, atlas_w, atlas_h


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="outputs/fleet/fleet_manifest.json")
    ap.add_argument("--indir", default="outputs/fleet")
    ap.add_argument("--outdir", default="outputs/atlas")
    ap.add_argument("--max-dim", type=int, default=256)
    ap.add_argument("--alpha-threshold", type=int, default=8,
                    help="ignore alpha below this value when finding the trim bbox (drops "
                         "sub-threshold matting specks); 0 = legacy any-nonzero-alpha behavior")
    ap.add_argument("--atlas-width", type=int, default=1024)
    ap.add_argument("--name", default="dwa_ships")
    ap.add_argument("--cell", type=int, default=0,
                    help="grid mode: keep full square cell at this px (no trim) so edge ports stay aligned")
    ap.add_argument("--cols", type=int, default=0, help="grid columns (0 = auto sqrt)")
    args = ap.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    (outdir / "sprites").mkdir(parents=True, exist_ok=True)

    man = json.loads(Path(args.manifest).read_text())
    frames = [(s["name"], indir / s["rgba"]) for s in man["ships"] if s.get("rgba")]

    # Grid mode keeps the full square cell (edge ports stay aligned for tiling); default mode
    # trims to the alpha bbox + downscales to max-dim (best for free-standing sprites).
    imgs = []
    for name, p in frames:
        if args.cell:
            im = Image.open(p).convert("RGBA").resize((args.cell, args.cell), Image.LANCZOS)
        else:
            im = trim_and_fit(p, args.max_dim, args.alpha_threshold)
        im.save(outdir / "sprites" / f"{name}.png")   # also keep standalone sprites
        imgs.append((name, im))

    if args.cell:
        cell = args.cell
        cols = args.cols or math.ceil(math.sqrt(len(imgs)))
        rows = math.ceil(len(imgs) / cols)
        placements = [((i % cols) * (cell + PAD), (i // cols) * (cell + PAD)) for i in range(len(imgs))]
        aw, ah = cols * cell + (cols - 1) * PAD, rows * cell + (rows - 1) * PAD
    else:
        placements, _, ah = shelf_pack([im.size for _, im in imgs], args.atlas_width)
        aw = max((x + im.size[0]) for (x, _), (_, im) in zip(placements, imgs))

    atlas = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
    descr = {"frames": {}, "meta": {"app": "asset-harness", "image": f"{args.name}.png",
                                    "format": "RGBA8888", "size": {"w": aw, "h": ah}, "scale": 1}}
    for (name, im), (x, y) in zip(imgs, placements):
        w, h = im.size
        atlas.paste(im, (x, y))
        descr["frames"][name] = {
            "frame": {"x": x, "y": y, "w": w, "h": h},
            "rotated": False, "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h},
            "sourceSize": {"w": w, "h": h},
        }

    atlas.save(outdir / f"{args.name}.png")
    (outdir / f"{args.name}.json").write_text(json.dumps(descr, indent=2))
    print(f"atlas {aw}x{ah} with {len(imgs)} frames -> {outdir/(args.name+'.png')}")
    for name, im in imgs:
        print(f"  {name}: {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
