"""Spike tool (WI 1371): read a flat-shaded face by its holes. The face is the connected region of skin
colour; eyes, brows and mouth are the non-skin regions it encloses. No face prior at all, which is the point."""
import sys, json
from collections import deque
from PIL import Image, ImageDraw
N = 256

def components(mask, want):
    seen = [[False] * N for _ in range(N)]
    out = []
    for y0 in range(N):
        for x0 in range(N):
            if seen[y0][x0] or mask[y0][x0] != want:
                continue
            q, comp, border = deque([(x0, y0)]), [], False
            seen[y0][x0] = True
            while q:
                x, y = q.popleft(); comp.append((x, y))
                if x in (0, N - 1) or y in (0, N - 1): border = True
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < N and 0 <= ny < N and not seen[ny][nx] and mask[ny][nx] == want:
                        seen[ny][nx] = True; q.append((nx, ny))
            out.append((comp, border))
    return out

def bbox(comp):
    xs, ys = [p[0] for p in comp], [p[1] for p in comp]
    return min(xs), min(ys), max(xs), max(ys)

def read(path, seed, tol):
    im = Image.open(path).convert("RGB").resize((N, N), Image.LANCZOS); px = im.load()
    sx, sy = int(seed[0] * N), int(seed[1] * N)
    patch = sorted(px[x, y] for x in range(sx - 4, sx + 5) for y in range(sy - 4, sy + 5))
    ref = patch[len(patch) // 2]
    skin = [[sum((px[x, y][c] - ref[c]) ** 2 for c in range(3)) ** 0.5 < tol for x in range(N)] for y in range(N)]
    face = max((c for c, _ in components(skin, True)), key=len)
    fx0, fy0, fx1, fy1 = bbox(face)
    inface = [[False] * N for _ in range(N)]
    for x, y in face: inface[y][x] = True
    holes = [c for c, border in components(inface, False) if not border and len(c) >= 12]
    k = 512 / N
    H = [{"area": len(c) * k * k, "box": [v * k for v in bbox(c)]} for c in holes]
    for h in H:
        x0, y0, x1, y1 = h["box"]; h["cx"], h["cy"], h["w"], h["h"] = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + k, y1 - y0 + k
    cx = (fx0 + fx1) / 2 * k; top, bot = fy0 * k, fy1 * k; fh = bot - top
    upper = [h for h in H if top + 0.15 * fh < h["cy"] < top + 0.70 * fh]
    eyes = {}
    for side, keep in (("L", lambda h: h["cx"] > cx), ("R", lambda h: h["cx"] < cx)):   # character's left = image right
        cand = [h for h in upper if keep(h)]
        if cand: eyes[side] = max(cand, key=lambda h: h["area"])
    brows = [h for h in H if eyes and h["cy"] < min(e["cy"] - e["h"] / 2 for e in eyes.values()) and h["w"] > 2 * h["h"]]
    lower = [h for h in H if h["cy"] > top + 0.62 * fh and abs(h["cx"] - cx) < 0.2 * (fx1 - fx0) * k]
    mouth = max(lower, key=lambda h: h["w"]) if lower else None
    f = {"face_w": (fx1 - fx0) * k, "face_h": fh, "top_y": top, "chin_y": bot, "holes": len(H)}
    if len(eyes) == 2:
        f.update(eye_spacing=eyes["L"]["cx"] - eyes["R"]["cx"], eye_y=(eyes["L"]["cy"] + eyes["R"]["cy"]) / 2,
                 eye_w=(eyes["L"]["w"] + eyes["R"]["w"]) / 2, eye_h=(eyes["L"]["h"] + eyes["R"]["h"]) / 2)
    if brows: f["brow_y"] = sum(b["cy"] for b in brows) / len(brows)
    if mouth: f.update(mouth_y=mouth["cy"], mouth_w=mouth["w"])
    big = im.resize((512, 512)); dr = ImageDraw.Draw(big)
    dr.rectangle((fx0 * k, top, fx1 * k, bot), outline=(255, 255, 0))
    for h in H: dr.rectangle(h["box"], outline=(0, 255, 0))
    for e in eyes.values(): dr.rectangle(e["box"], outline=(255, 0, 0), width=2)
    for b in brows: dr.rectangle(b["box"], outline=(255, 128, 0), width=2)
    if mouth: dr.rectangle(mouth["box"], outline=(0, 128, 255), width=2)
    return f, big

if __name__ == "__main__":
    tol = float(sys.argv[1]); res = {}; tiles = []
    for path in sys.argv[3:]:
        f, big = read(path, (0.5, 0.56), tol); res[path] = f; tiles.append(big)
        print(path, {k: round(v, 1) for k, v in f.items()})
    sheet = Image.new("RGB", (512 * len(tiles), 512)); [sheet.paste(t, (512 * i, 0)) for i, t in enumerate(tiles)]
    sheet.save(sys.argv[2] + ".png"); json.dump(res, open(sys.argv[2] + ".json", "w"), indent=1)
