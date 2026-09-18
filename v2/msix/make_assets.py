"""Tile, taskbar and Store logos for the MSIX package, generated from assets/icon.png."""
import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ART = Image.open(os.path.join(ROOT, "assets", "icon.png")).convert("RGBA")
navyTop, navyBottom = (32, 86, 150), (10, 32, 62)


def gradient(w, h, top=navyTop, bottom=navyBottom):
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    return img


def symbol(size):
    """Magnifier with bars; stays readable at taskbar sizes where the detailed art turns to mush."""
    ss = 8
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = round(S * (0.02 if size <= 24 else 0.05))
    tile = Image.new("L", (S, S), 0)
    ImageDraw.Draw(tile).rounded_rectangle((m, m, S - m, S - m), radius=S * 0.22, fill=255)
    img.paste(gradient(S, S), (0, 0), tile)

    d = ImageDraw.Draw(img)
    light = (236, 244, 255, 255)
    small = size <= 20
    cx = cy = S * 0.43
    r = S * (0.29 if small else 0.27)
    ring = S * (0.10 if small else 0.075 if size <= 32 else 0.065)
    d.line((cx + r * 0.62, cy + r * 0.62, S * 0.83, S * 0.83), fill=light, width=round(S * (0.15 if small else 0.12)))
    d.ellipse((S * 0.77, S * 0.77, S * 0.89, S * 0.89), fill=light)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=light)
    inner = r - ring
    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(14, 44, 82, 255))

    colors = [(52, 199, 89, 255), (255, 176, 32, 255), (47, 155, 255, 255)]
    heights = [0.34, 0.56, 0.80]
    if small:
        colors, heights = [colors[0], colors[2]], [0.45, 0.80]
    bw = inner * (0.52 if small else 0.34)
    gap = inner * 0.12
    x = cx - (len(colors) * bw + (len(colors) - 1) * gap) / 2
    base = cy + inner * 0.52
    for c, hgt in zip(colors, heights):
        d.rectangle((x, base - inner * 1.05 * hgt, x + bw, base), fill=c)
        x += bw + gap

    out = img.resize((size, size), Image.LANCZOS)
    if size <= 32:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    return out


def art(size):
    return ART.resize((size, size), Image.LANCZOS)


def wide(w, h):
    img = gradient(w, h)
    a = art(int(h * 0.86))
    img.paste(a, ((w - a.width) // 2, (h - a.height) // 2), a)
    return img


def build(outDir):
    os.makedirs(outDir, exist_ok=True)

    def save(img, name):
        img.save(os.path.join(outDir, name))

    for scale, px in ((100, 44), (125, 55), (150, 66), (200, 88), (400, 176)):
        save(symbol(px) if px <= 88 else art(px), f"Square44x44Logo.scale-{scale}.png")
    for t in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        img = symbol(t) if t <= 48 else art(t)
        save(img, f"Square44x44Logo.targetsize-{t}.png")
        save(img, f"Square44x44Logo.targetsize-{t}_altform-unplated.png")
    for scale, px in ((100, 150), (125, 188), (150, 225), (200, 300), (400, 600)):
        save(art(px), f"Square150x150Logo.scale-{scale}.png")
    for scale, (w, h) in ((100, (310, 150)), (125, (388, 188)), (150, (465, 225)), (200, (620, 300)), (400, (1240, 600))):
        save(wide(w, h), f"Wide310x150Logo.scale-{scale}.png")
    for scale, px in ((100, 50), (125, 63), (150, 75), (200, 100), (400, 200)):
        save(art(px), f"StoreLogo.scale-{scale}.png")


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "layout", "Assets"))
