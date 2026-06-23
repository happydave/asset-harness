#!/usr/bin/env python3
"""Generate a thruster-flame VFX sprite set (Z-Image on black) for engine particle systems.

Flames are emissive → rendered with additive blending where black = transparent, so we generate
on a pure black background and use the image directly (additive); we also emit an RGBA variant
(alpha = luminance) for alpha-blend pipelines. The engine (bevy_hanabi / Phaser) supplies the
motion; these are the sprites it consumes.

Outputs per flame: <name>.png (additive, on black) + <name>_rgba.png, and a preview montage.
"""
import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pbr-materials" / "prototypes"))
import gen_albedo  # noqa: E402  (generic Z-Image txt2img CLI/module)

SERVER = "http://ai2:8188"
HERE = pathlib.Path(__file__).parent
OUT = HERE / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

STYLE = "emissive VFX sprite on a pure solid black background, glowing, centered, isolated, no text"
FLAMES = [
    {"name": "plume", "size": 768, "seed": 71,
     "subject": "a vertical rocket engine exhaust flame plume, intense white-hot core fading through "
                "yellow and orange with a blue base, long tapering wispy tip"},
    {"name": "puff", "size": 512, "seed": 72,
     "subject": "a single soft round puff of glowing orange and yellow fire with a few ember sparks"},
    {"name": "spark", "size": 512, "seed": 73,
     "subject": "a scattering of small bright glowing orange embers and sparks streaking outward"},
]


def to_rgba(path: pathlib.Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    rgba = im.convert("RGBA")
    rgba.putalpha(im.convert("L"))  # luminance as alpha for alpha-blend use
    return rgba


def checker(sz: int, c: int = 32) -> Image.Image:
    im = Image.new("RGB", (sz, sz), (150, 150, 150))
    d = ImageDraw.Draw(im)
    for y in range(0, sz, c):
        for x in range(0, sz, c):
            if (x // c + y // c) % 2:
                d.rectangle([x, y, x + c, y + c], fill=(195, 195, 195))
    return im


def main() -> None:
    results = []
    for f in FLAMES:
        prompt = f"{f['subject']}, {STYLE}"
        src = gen_albedo.generate_albedo(SERVER, prompt, f["seed"], f["size"], OUT, f"flame_{f['name']}")
        rgba = to_rgba(src)
        rgba.save(OUT / f"flame_{f['name']}_rgba.png")
        results.append((f["name"], src, rgba))
        print("generated", f["name"], "->", src.name)

    th = 256
    mont = Image.new("RGB", (th * len(results), th * 2), (0, 0, 0))
    for i, (_, src, rgba) in enumerate(results):
        mont.paste(Image.open(src).convert("RGB").resize((th, th)), (i * th, 0))   # additive on black
        ch = checker(th)
        r = rgba.resize((th, th))
        ch.paste(r, (0, 0), r)                                                     # rgba over checker
        mont.paste(ch, (i * th, th))
    mont.save(OUT / "flames_montage.png")
    print("montage ->", OUT / "flames_montage.png")


if __name__ == "__main__":
    main()
