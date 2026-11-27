"""Drawing helpers: easing, fonts, text sprites, anti-aliased shapes, compositing.

Everything is drawn with Pillow onto RGBA layers. Product photos are only ever
scaled uniformly and moved - never recolored, warped, cropped or retouched.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

FONT_FILES = {
    "serif": "DMSerifDisplay-Regular.ttf",
    "serif_italic": "DMSerifDisplay-Italic.ttf",
    "sans": "Inter-Regular.otf",
    "sans_medium": "Inter-Medium.otf",
    "sans_semibold": "Inter-SemiBold.otf",
    "sans_bold": "Inter-Bold.otf",
    "sans_xbold": "Inter-ExtraBold.otf",
}

# ----------------------------------------------------------------- easing ---

def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def prog(t, start, dur):
    """0..1 progress of an animation that starts at `start` and lasts `dur`."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def lerp(a, b, p):
    return a + (b - a) * p


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_in_cubic(p):
    return p ** 3


def ease_in_out(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_expo(p):
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def ease_out_back(p, s=1.70158):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def damped(p, freq=2.2, decay=4.5):
    """Damped oscillation 1 -> 0, used for tag swings and wobbles."""
    return math.exp(-decay * p) * math.cos(2 * math.pi * freq * p)


# ------------------------------------------------------------------ fonts ---

@lru_cache(maxsize=None)
def font(key: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / FONT_FILES[key]), int(size))


@dataclass
class Spr:
    """A pre-rendered RGBA sprite. (ox, oy) is where the logical box starts."""
    img: Image.Image
    w: int          # logical (advance) width
    h: int          # logical height (ascent + descent)
    ox: int = 0
    oy: int = 0


_text_cache: dict = {}


def text_sprite(text, key, size, fill, tracking=0) -> Spr:
    k = (text, key, size, fill, tracking)
    if k in _text_cache:
        return _text_cache[k]
    f = font(key, size)
    asc, desc = f.getmetrics()
    if tracking:
        adv = sum(f.getlength(c) for c in text) + tracking * max(0, len(text) - 1)
    else:
        adv = f.getlength(text)
    pad = int(size * 0.25) + 4
    img = Image.new("RGBA", (int(adv) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = pad
        for c in text:
            d.text((x, pad), c, font=f, fill=fill, anchor="la")
            x += f.getlength(c) + tracking
    else:
        d.text((pad, pad), text, font=f, fill=fill, anchor="la")
    s = Spr(img, int(round(adv)), asc + desc, pad, pad)
    if len(_text_cache) > 6000:
        _text_cache.clear()
    _text_cache[k] = s
    return s


def text_width(text, key, size, tracking=0):
    f = font(key, size)
    if tracking:
        return sum(f.getlength(c) for c in text) + tracking * max(0, len(text) - 1)
    return f.getlength(text)


def wrap_words(words, key, size, max_w):
    """Greedy word wrap. Returns list of lines (each a list of words)."""
    space = text_width(" ", key, size)
    lines, cur, cur_w = [], [], 0.0
    for w in words:
        ww = text_width(w, key, size)
        if cur and cur_w + space + ww > max_w:
            lines.append(cur)
            cur, cur_w = [w], ww
        else:
            cur_w = cur_w + space + ww if cur else ww
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def fit_size(words, key, size, max_w, max_lines):
    """Shrink font size until the words wrap into max_lines."""
    while size > 24:
        lines = wrap_words(words, key, size, max_w)
        if len(lines) <= max_lines and all(
            text_width(" ".join(l), key, size) <= max_w for l in lines
        ):
            return size, lines
        size -= 4
    return size, wrap_words(words, key, size, max_w)


# ------------------------------------------------------------ compositing ---

def with_opacity(img, a):
    if a >= 0.999:
        return img
    im = img.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def paste(dst, img, x, y, opacity=1.0):
    """Alpha-composite img with its top-left at (x, y); clips to dst."""
    if opacity <= 0.004:
        return
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    ex, ey = min(img.width, dst.width - x), min(img.height, dst.height - y)
    if ex <= sx or ey <= sy:
        return
    if (sx, sy, ex, ey) != (0, 0, img.width, img.height):
        img = img.crop((sx, sy, ex, ey))
    if opacity < 0.999:
        img = with_opacity(img, opacity)
    dst.alpha_composite(img, (x + sx, y + sy))


def place(dst, img, cx, cy, scale=1.0, rot=0.0, opacity=1.0, anchor=(0.5, 0.5)):
    """Draw img so that its anchor point lands at (cx, cy)."""
    if opacity <= 0.004 or scale <= 0.01:
        return
    if abs(scale - 1.0) > 0.002:
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.BICUBIC,
        )
    if abs(rot) > 0.05:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    paste(dst, img, cx - img.width * anchor[0], cy - img.height * anchor[1], opacity)


def place_text(dst, spr: Spr, x, y, opacity=1.0, scale=1.0, rot=0.0):
    """Place a text sprite with its logical top-left at (x, y)."""
    if abs(scale - 1) < 0.002 and abs(rot) < 0.05:
        paste(dst, spr.img, x - spr.ox, y - spr.oy, opacity)
    else:
        cx = x + spr.w / 2
        cy = y + spr.h / 2
        # sprite center == logical center because padding is symmetric
        place(dst, spr.img, cx, cy, scale, rot, opacity)


# ----------------------------------------------------------------- shapes ---

SS = 3  # supersampling for anti-aliased shapes

_shape_cache: dict = {}


def _aa(key, w, h, draw_fn):
    if key in _shape_cache:
        return _shape_cache[key]
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(big), SS)
    img = big.resize((w, h), Image.LANCZOS)
    _shape_cache[key] = img
    return img


def rounded(w, h, r, fill, outline=None, width=0):
    w, h = int(w), int(h)

    def fn(d, s):
        d.rounded_rectangle(
            (0, 0, w * s - 1, h * s - 1), radius=r * s, fill=fill,
            outline=outline, width=width * s,
        )
    return _aa(("rr", w, h, r, fill, outline, width), w, h, fn)


def circle(dia, fill, outline=None, width=0):
    def fn(d, s):
        d.ellipse((0, 0, dia * s - 1, dia * s - 1), fill=fill, outline=outline, width=width * s)
    return _aa(("c", dia, fill, outline, width), dia, dia, fn)


def sparkle(size, fill):
    """Four-point star accent."""
    def fn(d, s):
        c = size * s / 2
        r1, r2 = c, c * 0.22
        pts = []
        for i in range(8):
            a = math.pi / 4 * i - math.pi / 2
            r = r1 if i % 2 == 0 else r2
            pts.append((c + r * math.cos(a), c + r * math.sin(a)))
        d.polygon(pts, fill=fill)
    return _aa(("sp", size, fill), size, size, fn)


def arrow_up(w, h, fill, stroke=10):
    def fn(d, s):
        cx = w * s / 2
        st = stroke * s
        d.line((cx, h * s, cx, st), fill=fill, width=st)
        d.line((cx - w * s * 0.42, w * s * 0.42 + st / 2, cx, st / 2), fill=fill, width=st, joint="curve")
        d.line((cx + w * s * 0.42, w * s * 0.42 + st / 2, cx, st / 2), fill=fill, width=st, joint="curve")
        r = st / 2
        for px, py in ((cx, h * s - r), (cx - w * s * 0.42, w * s * 0.42 + st / 2), (cx + w * s * 0.42, w * s * 0.42 + st / 2), (cx, st / 2)):
            d.ellipse((px - r, py - r, px + r, py + r), fill=fill)
    return _aa(("arr", w, h, fill, stroke), w, h, fn)


def stroke_path(dst, pts, p, color, width, ox=0, oy=0):
    """Draw the first fraction `p` of a polyline with round caps (anti-aliased)."""
    if p <= 0.001 or len(pts) < 2:
        return
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(segs)
    target = total * clamp(p)
    out = [pts[0]]
    acc = 0.0
    for i, L in enumerate(segs):
        if acc + L >= target:
            f = (target - acc) / L if L else 0
            out.append((lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f)))
            break
        acc += L
        out.append(pts[i + 1])
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    pad = width + 4
    x0, y0 = min(xs) - pad, min(ys) - pad
    bw, bh = int(max(xs) - x0 + pad), int(max(ys) - y0 + pad)
    big = Image.new("RGBA", (bw * SS, bh * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sp = [((x - x0) * SS, (y - y0) * SS) for x, y in out]
    d.line(sp, fill=color, width=int(width * SS), joint="curve")
    r = width * SS / 2
    for qx, qy in (sp[0], sp[-1]):
        d.ellipse((qx - r, qy - r, qx + r, qy + r), fill=color)
    img = big.resize((bw, bh), Image.LANCZOS)
    paste(dst, img, x0 + ox, y0 + oy)


def bezier(p0, p1, p2, p3, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        pts.append((
            mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
            mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return pts


def drop_shadow(img, blur=28, offset=(0, 18), color=(60, 40, 30), alpha=0.22):
    """Return (new_img, pad) with a soft shadow underneath img."""
    pad = blur * 2 + max(abs(offset[0]), abs(offset[1]))
    out = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, color + (0,))
    sh.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    out.paste(sh, (pad + offset[0], pad + offset[1]), sh)
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(img, (pad, pad))
    return out, pad


def fit_image(img, max_w, max_h):
    """Uniformly scale to fit inside max_w x max_h (aspect ratio preserved)."""
    s = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
