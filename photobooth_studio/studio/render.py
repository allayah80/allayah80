"""Deterministic renderers for each product type (no AI involved).

Every renderer takes the same ``Design`` (theme profile + seed) and a Palette,
so color variations share one identical layout.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import motifs
from .config import FONTS, spec
from .palettes import Palette, contrast, luminance, mix


@dataclass
class Design:
    theme: str
    profile: dict
    seed: int
    headline: str
    placeholder: str
    sizes: dict = field(default_factory=dict)  # ptype -> (w, h) overrides


# ---------------------------------------------------------------- fonts/text
@lru_cache(maxsize=256)
def font(font_spec: tuple, size: int) -> ImageFont.FreeTypeFont:
    fname, variation = font_spec
    f = ImageFont.truetype(str(FONTS / fname), max(6, int(size)))
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


def fit_font(draw, text, font_spec, max_w, max_h, start=None):
    size = int(start or max_h)
    while size > 8:
        f = font(font_spec, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= max_w and b - t <= max_h:
            return f
        size = int(size * 0.92)
    return font(font_spec, 8)


def _wrap_options(text, max_lines=3):
    words = text.split()
    yield text
    if len(words) < 2:
        return
    # split on the bullet first if present (e.g. "Names Here • 00.00.2027")
    if "•" in text:
        a, b = text.split("•", 1)
        yield a.strip() + "\n" + b.strip()
    for n in range(2, min(max_lines, len(words)) + 1):
        # greedy split into n lines of roughly equal character length
        target = len(text) / n
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) / 2 > target and len(lines) < n - 1:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        lines.append(cur)
        yield "\n".join(lines)


def best_layout(draw, text, font_spec, max_w, max_h):
    """Choose the line-wrapping that gives the largest font size."""
    best = None
    for cand in _wrap_options(text):
        lines = cand.count("\n") + 1
        f = fit_font(draw, cand, font_spec, max_w, max_h, start=max_h / lines)
        if best is None or f.size > best[1].size * 1.08:
            best = (cand, f)
    return best


def draw_text_center(img: Image.Image, text, font_spec, box, color, shadow=None, start=None,
                     halo=None, wrap=True):
    """Draw text centered in box=(x0,y0,x1,y1), wrapped and shrunk to fit.

    halo: optional background color drawn as a soft glow behind the text so it
    stays readable over busy artwork.
    """
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    if wrap:
        text, f = best_layout(d, text, font_spec, x1 - x0, y1 - y0)
    else:
        f = fit_font(d, text, font_spec, x1 - x0, y1 - y0, start)
    kw = dict(font=f, align="center", spacing=f.size * 0.15)
    l, t, r, b = d.multiline_textbbox((0, 0), text, **kw)
    x = x0 + (x1 - x0 - (r - l)) / 2 - l
    y = y0 + (y1 - y0 - (b - t)) / 2 - t
    if halo is not None:
        sw = max(2, int(f.size * 0.12))
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).multiline_text((x, y), text, fill=255, stroke_width=sw, stroke_fill=255, **kw)
        m = m.filter(ImageFilter.GaussianBlur(sw * 0.9)).point(lambda v: int(v * 0.8))
        hl = Image.new("RGBA", img.size, tuple(halo[:3]) + (0,))
        hl.putalpha(m)
        img.alpha_composite(hl)
        d = ImageDraw.Draw(img)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((x + shadow[0], y + shadow[1]), text, fill=shadow[2], **kw)
        sh = sh.filter(ImageFilter.GaussianBlur(max(1, abs(shadow[0]))))
        img.alpha_composite(sh)
        d = ImageDraw.Draw(img)
    d.multiline_text((x, y), text, fill=tuple(color[:3]) + (255,), **kw)
    return f


# ---------------------------------------------------------------- helpers
def background(size, pal: Palette, seed: int) -> Image.Image:
    w, h = size
    top = np.array(mix(pal.bg, (255, 255, 255), 0.12), dtype=np.float32)
    bot = np.array(mix(pal.bg, pal.primary, 0.18), dtype=np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    grad = top * (1 - t) + bot * t
    grad = np.repeat(grad, w, axis=1)
    # soft radial glow in the middle
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    glow = np.clip(1 - r, 0, 1)[..., None] * 0.10
    grad = grad * (1 - glow) + 255 * glow
    arr = np.clip(grad + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def punch(img: Image.Image, rect, radius, outline=None, width=0):
    """Make a rounded-rect photo window fully transparent."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(rect, radius=radius, fill=255)
    a = np.array(img.getchannel("A"))
    a[np.array(mask) > 0] = 0
    img.putalpha(Image.fromarray(a))
    if outline is not None and width:
        o = (rect[0] - width, rect[1] - width, rect[2] + width, rect[3] + width)
        ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
        rd = ImageDraw.Draw(ring)
        rd.rounded_rectangle(o, radius=radius + width, outline=tuple(outline[:3]) + (255,), width=width)
        img.alpha_composite(ring)


def compose_base(size, design: Design, pal: Palette, keepout, density=1.0) -> Image.Image:
    img = background(size, pal, design.seed)
    img.alpha_composite(motifs.draw_motifs(size, design.profile["motifs"], pal, design.seed, keepout, density))
    img.alpha_composite(motifs.draw_frame(size, design.profile["frame"], pal))
    return img


def _text_colors(pal: Palette, bg_rgb):
    head = pal.primary if contrast(pal.primary, bg_rgb) >= 3.0 else pal.text_on(bg_rgb)
    body = pal.text_on(bg_rgb)
    return head, body


def _region_color(img: Image.Image, box):
    crop = img.crop(tuple(int(v) for v in box)).convert("RGB").resize((8, 8))
    return tuple(int(v) for v in np.array(crop).reshape(-1, 3).mean(axis=0))


def _text_block(img, design, pal, box, with_text, head_ratio=0.62):
    """Headline + placeholder line inside box."""
    if not with_text:
        return
    x0, y0, x1, y1 = box
    bgc = _region_color(img, box)
    head_c, body_c = _text_colors(pal, bgc)
    hh = (y1 - y0) * head_ratio
    halo = pal.bg
    draw_text_center(img, design.headline, design.profile["title_font"], (x0, y0, x1, y0 + hh), head_c, halo=halo)
    # keep the placeholder line visually secondary (max ~45% of headline height)
    sub_h = min(y1 - (y0 + hh + (y1 - y0) * 0.06), hh * 0.45)
    sy = y0 + hh + (y1 - y0) * 0.06
    draw_text_center(img, design.placeholder, design.profile["body_font"],
                     (x0 + (x1 - x0) * 0.06, sy, x1 - (x1 - x0) * 0.06, sy + sub_h), body_c, halo=halo)


def _set_dpi(img, dpi):
    img.info["dpi"] = (dpi, dpi)
    return img


# ---------------------------------------------------------------- products
def welcome_screen(design: Design, pal: Palette, with_text=True, size=None) -> Image.Image:
    s = spec("welcome_screen", size or design.sizes.get("welcome_screen"))
    w, h = s["size"]
    keep = [(w * 0.18, h * 0.2, w * 0.82, h * 0.86)]
    img = compose_base((w, h), design, pal, keep)
    if with_text:
        welcome_text(img, design, pal)
    return _set_dpi(img.convert("RGB"), s["dpi"])


def welcome_text(img: Image.Image, design: Design, pal: Palette, cta_alpha: float = 1.0, include_cta=True):
    w, h = img.size
    portrait = h > w
    tb = (w * 0.16, h * (0.22 if not portrait else 0.28), w * 0.84, h * (0.62 if not portrait else 0.56))
    _text_block(img, design, pal, tb, True, head_ratio=0.68)
    if include_cta:
        cta(img, pal, cta_alpha)


def cta(img: Image.Image, pal: Palette, alpha: float = 1.0, label="TOUCH TO START"):
    w, h = img.size
    bw, bh = min(w, h) * 0.62, min(w, h) * 0.11
    cx, cy = w / 2, h * 0.75
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    d.rounded_rectangle(box, radius=bh / 2, fill=tuple(pal.primary[:3]) + (255,),
                        outline=tuple(pal.accent[:3]) + (255,), width=max(2, int(bh * 0.05)))
    draw_text_center(layer, label, ("Montserrat-VF.ttf", "Bold"),
                     (box[0] + bh * 0.4, box[1] + bh * 0.28, box[2] - bh * 0.4, box[3] - bh * 0.28),
                     pal.text_on(pal.primary))
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    img.alpha_composite(layer)


def strip_2x6(design: Design, pal: Palette, with_text=True, size=None) -> Image.Image:
    s = spec("strip_2x6", size or design.sizes.get("strip_2x6"))
    w, h = s["size"]
    n = s.get("photos", 3)
    m = w * 0.07
    footer = h * 0.2
    gap = w * 0.05
    ph = (h - footer - m - gap * (n - 1) - m * 0.4) / n
    windows = []
    y = m
    for _ in range(n):
        windows.append((m, y, w - m, y + ph))
        y += ph + gap
    keep = [(0, h - footer, w, h - m * 0.5)] if with_text else []
    img = compose_base((w, h), design, pal, keep + windows, density=0.8)
    for r in windows:
        punch(img, r, radius=w * 0.025, outline=pal.accent, width=max(2, int(w * 0.006)))
    _text_block(img, design, pal, (m * 0.6, h - footer + m * 0.1, w - m * 0.6, h - m * 0.8), with_text)
    img.info["windows"] = windows
    return _set_dpi(img, s["dpi"])


def strip_double(strip: Image.Image) -> Image.Image:
    """Two 2x6 strips side by side on a 4x6 sheet (how most printers cut strips)."""
    w, h = strip.size
    sheet = Image.new("RGBA", (w * 2, h), (0, 0, 0, 0))
    sheet.paste(strip, (0, 0))
    sheet.paste(strip, (w, 0))
    sheet.info["windows"] = [(x0 + dx, y0, x1 + dx, y1) for dx in (0, w)
                             for (x0, y0, x1, y1) in strip.info.get("windows", [])]
    return _set_dpi(sheet, 300)


def overlay_4x6(design: Design, pal: Palette, with_text=True, size=None) -> Image.Image:
    s = spec("overlay_4x6", size or design.sizes.get("overlay_4x6"))
    w, h = s["size"]
    m = min(w, h) * 0.06
    if w >= h:  # landscape: photo left, text panel right
        panel = w * 0.3
        win = (m, m, w - panel, h - m)
        tbox = (w - panel + m * 0.4, h * 0.2, w - m * 0.8, h * 0.8)
    else:       # portrait: photo top, text band bottom
        band = h * 0.22
        win = (m, m, w - m, h - band)
        tbox = (m, h - band + m * 0.3, w - m, h - m * 0.8)
    img = compose_base((w, h), design, pal, [win, tbox] if with_text else [win])
    punch(img, win, radius=m * 0.35, outline=pal.accent, width=max(3, int(m * 0.08)))
    _text_block(img, design, pal, tbox, with_text, head_ratio=0.55 if w >= h else 0.62)
    img.info["windows"] = [win]
    return _set_dpi(img, s["dpi"])


def gif_overlay(design: Design, pal: Palette, with_text=True, size=None) -> Image.Image:
    s = spec("gif_overlay", size or design.sizes.get("gif_overlay"))
    w, h = s["size"]
    m = min(w, h) * 0.05
    band = h * 0.17
    win = (m, m, w - m, h - band)
    tbox = (w * 0.1, h - band + m * 0.15, w * 0.9, h - m * 0.6)
    img = compose_base((w, h), design, pal, [win, tbox] if with_text else [win], density=0.7)
    punch(img, win, radius=m * 0.5, outline=pal.accent, width=max(3, int(m * 0.08)))
    _text_block(img, design, pal, tbox, with_text, head_ratio=0.62)
    img.info["windows"] = [win]
    return _set_dpi(img, s["dpi"])


def button(design: Design, pal: Palette, label: str, size=None) -> Image.Image:
    s = spec("buttons", size or design.sizes.get("buttons"))
    w, h = s["size"]
    ss = 3
    W, H = w * ss, h * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = H * 0.08
    box = (pad, pad, W - pad, H - pad)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((box[0], box[1] + pad * 0.5, box[2], box[3] + pad * 0.5),
                                         radius=(H - 2 * pad) / 2, fill=(0, 0, 0, 70))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(pad * 0.4)))
    d = ImageDraw.Draw(img)
    top = mix(pal.primary, (255, 255, 255), 0.12)
    d.rounded_rectangle(box, radius=(H - 2 * pad) / 2, fill=tuple(top) + (255,),
                        outline=tuple(pal.accent) + (255,), width=int(H * 0.035))
    inner = (box[0] + H * 0.06, box[1] + H * 0.06, box[2] - H * 0.06, box[3] - H * 0.06)
    d.rounded_rectangle(inner, radius=(inner[3] - inner[1]) / 2,
                        outline=tuple(mix(pal.accent, (255, 255, 255), 0.4)) + (150,), width=int(H * 0.012))
    rng = random.Random(f"{design.seed}-btn-{label}")
    for side in (-1, 1):
        cx = W / 2 + side * (W / 2 - pad - H * 0.32)
        motifs.sparkle(d, cx, H / 2, H * 0.1, tuple(pal.accent) + (255,), rng.choice([0, 0.78]))
    draw_text_center(img, label, ("Montserrat-VF.ttf", "ExtraBold"),
                     (W * 0.2, H * 0.3, W * 0.8, H * 0.7), pal.text_on(top))
    out = img.resize((w, h), Image.LANCZOS)
    return _set_dpi(out, s["dpi"])


RENDERERS = {
    "welcome_screen": welcome_screen,
    "strip_2x6": strip_2x6,
    "overlay_4x6": overlay_4x6,
    "gif_overlay": gif_overlay,
}


def save_png(img: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    dpi = img.info.get("dpi", (72, 72))
    img.save(path, "PNG", dpi=dpi, compress_level=6)
    return path


def is_dark(pal: Palette) -> bool:
    return luminance(pal.bg) < 0.25
