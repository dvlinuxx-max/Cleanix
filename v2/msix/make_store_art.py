"""Store listing artwork: 1:1 logo, 2:3 poster, 1:1 box art and 16:9 hero, all in the app's navy palette."""
import os
from PIL import Image, ImageDraw, ImageFont

import make_assets as ma

OUT = os.path.join(ma.HERE, "store", "logos")
FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT = r"C:\Windows\Fonts\segoeui.ttf"
ACCENTS = [(52, 199, 89), (255, 176, 32), (47, 155, 255)]


def canvas(w, h):
    img = ma.gradient(w, h)
    d = ImageDraw.Draw(img)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((w * 0.15, h * 0.05, w * 0.85, h * 0.75), fill=(60, 130, 210, 40))
    img.alpha_composite(glow)
    return img, d


def accent_bars(d, cx, y, width):
    seg = width / 3
    for i, c in enumerate(ACCENTS):
        x0 = cx - width / 2 + i * seg
        d.rounded_rectangle((x0 + seg * 0.08, y, x0 + seg * 0.92, y + max(4, width * 0.025)), radius=4, fill=c + (255,))


def centered(d, text, font, cx, y, fill):
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2 - box[0], y), text, font=font, fill=fill)


def logo(size=300):
    return ma.art(size)


def poster(w=720, h=1080):
    img, d = canvas(w, h)
    a = ma.art(int(w * 0.72))
    img.alpha_composite(a, ((w - a.width) // 2, int(h * 0.18)))
    d = ImageDraw.Draw(img)
    centered(d, "Cleanix", ImageFont.truetype(FONT_BOLD, int(w * 0.15)), w / 2, int(h * 0.70), (255, 255, 255))
    accent_bars(d, w / 2, int(h * 0.84), w * 0.5)
    return img


def boxart(size=1080):
    img, d = canvas(size, size)
    a = ma.art(int(size * 0.58))
    img.alpha_composite(a, ((size - a.width) // 2, int(size * 0.12)))
    d = ImageDraw.Draw(img)
    centered(d, "Cleanix", ImageFont.truetype(FONT_BOLD, int(size * 0.12)), size / 2, int(size * 0.71), (255, 255, 255))
    accent_bars(d, size / 2, int(size * 0.88), size * 0.4)
    return img


def hero(w=1920, h=1080):
    img, d = canvas(w, h)
    a = ma.art(int(h * 0.62))
    img.alpha_composite(a, (int(w * 0.56), (h - a.height) // 2))
    d = ImageDraw.Draw(img)
    d.text((int(w * 0.10), int(h * 0.34)), "Cleanix", font=ImageFont.truetype(FONT_BOLD, int(h * 0.16)),
           fill=(255, 255, 255))
    d.text((int(w * 0.105), int(h * 0.55)), "Disk space analyzer and cleaner",
           font=ImageFont.truetype(FONT, int(h * 0.045)), fill=(182, 198, 219))
    seg_w = w * 0.08
    for i, c in enumerate(ACCENTS):
        x0 = w * 0.105 + i * (seg_w + 14)
        d.rounded_rectangle((x0, h * 0.64, x0 + seg_w, h * 0.64 + 10), radius=5, fill=c + (255,))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    logo().save(os.path.join(OUT, "store-logo-300x300.png"))
    poster().convert("RGB").save(os.path.join(OUT, "poster-720x1080.png"))
    boxart().convert("RGB").save(os.path.join(OUT, "boxart-1080x1080.png"))
    hero().convert("RGB").save(os.path.join(OUT, "hero-1920x1080.png"))
    print(sorted(os.listdir(OUT)))
