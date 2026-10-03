"""Labelled comparison sheets: rows and columns named in the image."""
from PIL import Image, ImageDraw

CELL, PAD, HEAD, LEFT = 300, 8, 28, 190


def sheet(out, columns, rows, title=""):
    """rows: [(label, [image path per column])]."""
    w = LEFT + len(columns) * (CELL + PAD)
    h = HEAD + (24 if title else 0) + len(rows) * (CELL + PAD)
    img = Image.new("RGB", (w, h), (40, 40, 40))
    d = ImageDraw.Draw(img)
    top = 0
    if title:
        d.text((8, 6), title, fill=(255, 255, 255))
        top = 24
    for c, name in enumerate(columns):
        d.text((LEFT + c * (CELL + PAD) + 6, top + 8), name, fill=(255, 255, 255))
    for r, (label, paths) in enumerate(rows):
        y = top + HEAD + r * (CELL + PAD)
        d.text((8, y + CELL // 2), label, fill=(255, 255, 255))
        for c, p in enumerate(paths):
            im = Image.open(p).convert("RGBA")
            bg = Image.new("RGBA", im.size, (90, 90, 90, 255))
            bg.alpha_composite(im)
            img.paste(bg.convert("RGB").resize((CELL, CELL)), (LEFT + c * (CELL + PAD), y))
    img.save(out)
    return out
