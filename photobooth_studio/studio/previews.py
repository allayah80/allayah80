"""Professional listing preview images (mockups), rendered deterministically.

Sample "guest photos" are abstract silhouettes generated in code, so no
real people, stock photos or model releases are involved.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import render, stores
from .config import PRODUCT_SPECS, spec
from .palettes import Palette, mix, smart_title, soft_bg

W, H = 2400, 1800  # 4:3, large enough for marketplace zoom
SANS = ("Montserrat-VF.ttf", "SemiBold")
SANS_B = ("Montserrat-VF.ttf", "ExtraBold")


# ---------------------------------------------------------------- sample photos
def sample_photo(size, seed) -> Image.Image:
    w, h = size
    rng = random.Random(seed)
    warm = [(236, 214, 196), (205, 190, 220), (190, 215, 225), (230, 200, 170), (210, 225, 200)]
    top, bot = rng.choice(warm), mix(rng.choice(warm), (90, 80, 90), 0.35)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    img = Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    for _ in range(6):  # background lights
        x, y, r = rng.uniform(0, w), rng.uniform(0, h * 0.5), rng.uniform(0.04, 0.1) * min(w, h)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 235, 70))
    img = img.filter(ImageFilter.GaussianBlur(min(w, h) * 0.02))
    d = ImageDraw.Draw(img)
    n = rng.choice([1, 2, 2, 3])
    tones = [(120, 96, 92), (88, 74, 80), (150, 120, 108), (104, 92, 110)]
    for i in range(n):
        cx = w * (i + 1) / (n + 1) + rng.uniform(-0.04, 0.04) * w
        s = min(w / (n + 0.6), h) * rng.uniform(0.42, 0.5)
        col = rng.choice(tones) + (255,)
        head_y = h - s * 1.25
        d.ellipse([cx - s * 0.22, head_y - s * 0.27, cx + s * 0.22, head_y + s * 0.27], fill=col)
        d.rounded_rectangle([cx - s * 0.5, head_y + s * 0.32, cx + s * 0.5, h + s * 0.3], radius=s * 0.35, fill=col)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def fill_windows(overlay: Image.Image, windows, seed) -> Image.Image:
    """Put sample photos behind an overlay's transparent windows."""
    out = Image.new("RGBA", overlay.size, (255, 255, 255, 255))
    for i, (x0, y0, x1, y1) in enumerate(windows):
        ph = sample_photo((int(x1 - x0) + 2, int(y1 - y0) + 2), f"{seed}-{i}")
        out.alpha_composite(ph, dest=(int(x0), int(y0)))
    out.alpha_composite(overlay)
    return out


# ---------------------------------------------------------------- helpers
def shadowed(img: Image.Image, blur=18, offset=(10, 16), opacity=90) -> Image.Image:
    pad = blur * 3
    canvas = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    mask = Image.new("L", canvas.size, 0)
    mask.paste(img.getchannel("A").point(lambda v: opacity if v > 0 else 0), (pad + offset[0], pad + offset[1]))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    sh = Image.new("RGBA", canvas.size, (20, 20, 30, 0))
    sh.putalpha(mask)
    canvas.alpha_composite(sh)
    canvas.alpha_composite(img, dest=(pad, pad))
    return canvas


def place(canvas, img, cx, cy, max_w, max_h, angle=0, shadow=True):
    im = img.copy().convert("RGBA")
    im.thumbnail((int(max_w), int(max_h)), Image.LANCZOS)
    if angle:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    if shadow:
        im = shadowed(im, blur=max(6, int(min(im.size) * 0.03)))
    canvas.alpha_composite(im, dest=(int(cx - im.width / 2), int(cy - im.height / 2)))


def device(screen: Image.Image) -> Image.Image:
    """Wrap a screen design in a simple tablet/monitor bezel."""
    sw, sh = screen.size
    b = int(min(sw, sh) * 0.045)
    dev = Image.new("RGBA", (sw + 2 * b, sh + 2 * b), (0, 0, 0, 0))
    d = ImageDraw.Draw(dev)
    d.rounded_rectangle([0, 0, dev.width - 1, dev.height - 1], radius=b * 1.4, fill=(28, 28, 32, 255))
    d.rounded_rectangle([3, 3, dev.width - 4, dev.height - 4], radius=b * 1.3, outline=(70, 70, 78, 255), width=2)
    dev.paste(screen.convert("RGB"), (b, b))
    return dev


def backdrop(pal: Palette) -> Image.Image:
    c1 = soft_bg(pal)
    c2 = mix(c1, pal.primary, 0.25)
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t
    return Image.fromarray(np.repeat(arr, W, axis=1).astype(np.uint8), "RGB").convert("RGBA")


def header(canvas, pal: Palette, title, subtitle=None):
    bg = soft_bg(pal)
    tc = pal.text_on(bg)
    render.draw_text_center(canvas, title, SANS_B, (W * 0.06, H * 0.035, W * 0.94, H * 0.115), tc)
    if subtitle:
        render.draw_text_center(canvas, subtitle, SANS, (W * 0.15, H * 0.12, W * 0.85, H * 0.165),
                                mix(tc, bg, 0.25))


def watermark(canvas: Image.Image, text="PREVIEW"):
    layer = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = render.font(SANS_B, 70)
    for y in range(0, H * 2, 420):
        for x in range(-400 + (y // 420 % 2) * 300, W * 2, 700):
            d.text((x, y), text, font=f, fill=(255, 255, 255, 34))
    layer = layer.rotate(28, resample=Image.BICUBIC).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    canvas.alpha_composite(layer)


def save(canvas: Image.Image, path: Path, wm: bool) -> Path:
    if wm:
        watermark(canvas)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path, "JPEG", quality=90, optimize=True, dpi=(72, 72))
    return path


# ---------------------------------------------------------------- loaders
class Assets:
    """Re-renders product art in memory (cheap) so we know the photo windows."""

    def __init__(self, b):
        self.b = b

    def get(self, ptype, pal, with_text=True):
        size = spec(ptype, self.b.size_for(ptype))["size"]
        return render.RENDERERS[ptype](self.b.design, pal, with_text=with_text, size=size)

    def filled(self, ptype, pal, seed=0):
        img = self.get(ptype, pal)
        if "windows" in img.info:
            return fill_windows(img, img.info["windows"], f"{self.b.design.seed}-{ptype}-{seed}")
        return img


# ---------------------------------------------------------------- pages
def build_all(b) -> list[Path]:
    """b is a pipeline.Builder. Returns the list of preview files."""
    types = b.job["product_types"]
    pals = b.palettes
    pal = pals[0]
    A = Assets(b)
    out = b.root / "previews"
    wm = b.settings.get("preview_watermark", True)
    theme = smart_title(b.job["theme"].strip())
    files = []
    n_col = f"{len(pals)} Color Variations"

    # 1. hero
    c = backdrop(pal)
    header(c, pal, f"{theme} Photo Booth Templates", f"{n_col}  •  Instant Download  •  Commercial Use")
    if "welcome_screen" in types or "welcome_video" in types:
        place(c, device(render.welcome_screen(b.design, pal, size=spec("welcome_screen", b.size_for("welcome_screen"))["size"])),
              W * 0.42, H * 0.45, W * 0.64, H * 0.5)
    if "strip_2x6" in types:
        place(c, A.filled("strip_2x6", pal, 1), W * 0.86, H * 0.6, W * 0.22, H * 0.74, angle=-4)
    if "overlay_4x6" in types:
        place(c, A.filled("overlay_4x6", pal, 2), W * 0.22, H * 0.8, W * 0.36, H * 0.3, angle=3)
    if "gif_overlay" in types:
        place(c, A.filled("gif_overlay", pal, 3), W * 0.6, H * 0.84, W * 0.2, H * 0.25, angle=-2)
    files.append(save(c, out / "01_hero.jpg", wm))

    # 2. color variations (welcome screens or overlays)
    key = "welcome_screen" if ("welcome_screen" in types or "welcome_video" in types) else next(
        (t for t in ("overlay_4x6", "gif_overlay", "strip_2x6") if t in types), None)
    if key and len(pals) > 1:
        c = backdrop(pal)
        header(c, pal, n_col, "Every design is included in each color")
        cols = 2 if len(pals) <= 4 else 3
        rows = math.ceil(len(pals) / cols)
        cw, ch = W * 0.9 / cols, H * 0.78 / rows
        for i, p in enumerate(pals):
            img = (render.welcome_screen(b.design, p, size=spec("welcome_screen", b.size_for("welcome_screen"))["size"])
                   if key == "welcome_screen" else A.filled(key, p, i))
            x = W * 0.05 + (i % cols + 0.5) * cw
            y = H * 0.2 + (i // cols + 0.45) * ch
            place(c, img, x, y, cw * 0.9, ch * 0.78)
            render.draw_text_center(c, p.name, SANS, (x - cw * 0.4, y + ch * 0.4, x + cw * 0.4, y + ch * 0.5),
                                    pal.text_on(soft_bg(pal)))
        files.append(save(c, out / "02_color_variations.jpg", wm))

    # 3. print templates (strips + 4x6)
    if "strip_2x6" in types or "overlay_4x6" in types:
        c = backdrop(pal)
        header(c, pal, "Print Templates", "300 DPI  •  Transparent photo areas  •  Blank + text versions")
        x = W * 0.12
        if "strip_2x6" in types:
            for i, p in enumerate(pals[:3]):
                place(c, A.filled("strip_2x6", p, 10 + i), x, H * 0.58, W * 0.16, H * 0.66, angle=(i - 1) * 2)
                x += W * 0.155
        if "overlay_4x6" in types:
            ox = (x + W * 0.97) / 2 + W * 0.02
            place(c, A.filled("overlay_4x6", pal, 20), ox, H * 0.42, W * 0.94 - x, H * 0.38, angle=-2)
            if len(pals) > 1:
                place(c, A.filled("overlay_4x6", pals[1], 21), ox, H * 0.78, W * 0.94 - x, H * 0.34, angle=2)
        files.append(save(c, out / "03_print_templates.jpg", wm))

    # 4. GIF overlay + buttons
    if "gif_overlay" in types or "buttons" in types:
        c = backdrop(pal)
        header(c, pal, "GIF Overlays & Booth Buttons", "Transparent PNGs ready for your booth software")
        if "gif_overlay" in types:
            for i, p in enumerate(pals[:2]):
                place(c, A.filled("gif_overlay", p, 30 + i), W * (0.2 + 0.32 * i), H * 0.57, W * 0.3, H * 0.62)
        if "buttons" in types:
            labels = PRODUCT_SPECS["buttons"]["labels"]
            bsize = spec("buttons", b.size_for("buttons"))["size"]
            x0 = W * 0.84 if "gif_overlay" in types else W * 0.5
            n = min(len(labels), 8)
            for i, lab in enumerate(labels[:n]):
                col = 0 if "gif_overlay" in types else i % 2
                row = i if "gif_overlay" in types else i // 2
                step = H * 0.68 / (n if "gif_overlay" in types else math.ceil(n / 2))
                cx = x0 + (col - (0 if "gif_overlay" in types else 0.5)) * W * 0.3
                place(c, render.button(b.design, pal, lab, bsize), cx, H * 0.24 + step * (row + 0.5),
                      W * 0.24, step * 0.9, shadow=False)
        files.append(save(c, out / "04_gif_and_buttons.jpg", wm))

    # 5. what's included
    c = backdrop(pal)
    header(c, pal, "What's Included", f"SKU {b.sku}")
    tc = pal.text_on(soft_bg(pal))
    lines = []
    for t in types:
        w_, h_ = spec(t, b.size_for(t))["size"]
        lines.append(f"{PRODUCT_SPECS[t]['label']}  —  {w_}x{h_}px {'MP4 loop' if t == 'welcome_video' else 'PNG'}")
    lines += [f"{len(pals)} colors: {', '.join(p.name for p in pals)}", "Blank + text versions of print designs",
              "Commercial license for your booth business", "Instant digital download (ZIP)"]
    y = H * 0.22
    step = min(H * 0.085, H * 0.7 / len(lines))
    for ln in lines:
        d = ImageDraw.Draw(c)
        r = step * 0.18
        d.ellipse([W * 0.12 - r, y + step * 0.5 - r, W * 0.12 + r, y + step * 0.5 + r], fill=tuple(pal.accent) + (255,))
        f = render.fit_font(d, ln, SANS, W * 0.74, step * 0.55)
        d.text((W * 0.15, y + step * 0.5), ln, font=f, fill=tuple(tc) + (255,), anchor="lm")
        y += step
    files.append(save(c, out / "05_whats_included.jpg", False))

    # 6. animated GIF preview of the GIF overlay
    if "gif_overlay" in types:
        ov = A.get("gif_overlay", pal)
        frames = []
        for i in range(4):
            fr = fill_windows(ov, ov.info["windows"], f"{b.design.seed}-gif-{i}").convert("RGB")
            fr.thumbnail((540, 540))
            frames.append(fr)
        gp = out / "06_gif_overlay_preview.gif"
        frames[0].save(gp, save_all=True, append_images=frames[1:], duration=450, loop=0, optimize=True)
        files.append(gp)
    if "shopify" in stores.enabled(b.settings):
        files += square_versions([f for f in files if f.suffix == ".jpg"], pal, out / "square")
    return files


def square_versions(paths: list[Path], pal: Palette, out: Path, size: int = 2048) -> list[Path]:
    """Square copies of the 4:3 previews (Shopify themes crop to square)."""
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        top, bottom = im.getpixel((im.width // 2, 2)), im.getpixel((im.width // 2, im.height - 3))
        t = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
        arr = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
        sq = Image.fromarray(np.repeat(arr, size, axis=1).astype(np.uint8), "RGB")
        im = im.resize((size, round(im.height * size / im.width)), Image.LANCZOS)
        sq.paste(im, (0, (size - im.height) // 2))
        dst = out / f"{p.stem}_square.jpg"
        sq.save(dst, "JPEG", quality=90, optimize=True, dpi=(72, 72))
        res.append(dst)
    return res
