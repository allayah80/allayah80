"""Procedural decorative artwork. Everything is drawn from geometry (no clip-art,
no downloaded images), so the designs are 100% original and safe to sell.

All drawing happens on a supersampled RGBA layer that the caller downsizes,
which gives smooth anti-aliased edges.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from .palettes import Palette, mix

Rect = tuple[float, float, float, float]


def _rot(points, cx, cy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in points]


def _rgba(c, a=255):
    return (int(c[0]), int(c[1]), int(c[2]), int(a))


# ---------------------------------------------------------------- primitives
def star(d, cx, cy, r, color, ang=0.0, points=5, inner=0.45):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = ang - math.pi / 2 + i * math.pi / points
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def sparkle(d, cx, cy, r, color, ang=0.0):
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.16
        a = ang + i * math.pi / 4
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def heart(d, cx, cy, r, color, ang=0.0):
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((x * r / 17, y * r / 17))
    d.polygon(_rot(pts, cx, cy, ang), fill=color)


def leaf(d, x0, y0, length, width, ang, color):
    pts = []
    n = 24
    for i in range(n + 1):
        t = i / n
        pts.append((t * length, math.sin(math.pi * t) ** 0.9 * width))
    for i in range(n, -1, -1):
        t = i / n
        pts.append((t * length, -math.sin(math.pi * t) ** 0.9 * width))
    d.polygon(_rot(pts, x0, y0, ang), fill=color)


def sprig(d, x, y, length, ang, color, color2, rng, scale):
    """A botanical branch: curved stem with alternating leaves."""
    pts = []
    bend = rng.uniform(-0.35, 0.35)
    n = 30
    for i in range(n + 1):
        t = i / n
        a = ang + bend * t
        pts.append((x + math.cos(a) * length * t, y + math.sin(a) * length * t))
    d.line(pts, fill=color, width=max(2, int(3 * scale)))
    count = rng.randint(6, 9)
    for i in range(1, count + 1):
        t = i / (count + 1)
        px, py = pts[int(t * n)]
        a = ang + bend * t
        side = 1 if i % 2 else -1
        la = a + side * rng.uniform(0.55, 0.9)
        ll = length * rng.uniform(0.16, 0.24) * (1.1 - t * 0.4)
        leaf(d, px, py, ll, ll * 0.32, la, color if i % 3 else color2)
    leaf(d, *pts[-1], length * 0.18, length * 0.06, ang + bend, color)


def snowflake(d, cx, cy, r, color, ang, w):
    for k in range(6):
        a = ang + k * math.pi / 3
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=color, width=w)
        for f in (0.45, 0.72):
            bx, by = cx + r * f * math.cos(a), cy + r * f * math.sin(a)
            for s in (-1, 1):
                b = a + s * math.pi / 4
                ln = r * 0.28 * (1.2 - f)
                d.line([(bx, by), (bx + ln * math.cos(b), by + ln * math.sin(b))], fill=color, width=w)


def balloon(d, cx, cy, r, color, ang, scale):
    w, h = r, r * 1.22
    d.ellipse([cx - w, cy - h, cx + w, cy + h], fill=color)
    hl = _rgba((255, 255, 255), 70)
    d.ellipse([cx - w * 0.55, cy - h * 0.7, cx - w * 0.15, cy - h * 0.15], fill=hl)
    ky = cy + h
    d.polygon([(cx, ky - 2), (cx - r * 0.12, ky + r * 0.16), (cx + r * 0.12, ky + r * 0.16)], fill=color)
    pts = []
    for i in range(30):
        t = i / 29
        pts.append((cx + math.sin(t * math.pi * 3 + ang) * r * 0.12, ky + r * 0.16 + t * r * 2.2))
    d.line(pts, fill=_rgba(mix(color[:3], (120, 120, 120), 0.4), 200), width=max(1, int(2 * scale)))


def pumpkin(d, cx, cy, r, color, stem):
    for dx, sc in ((-0.45, 0.62), (0.45, 0.62), (0, 0.7)):
        d.ellipse([cx + dx * r - r * sc, cy - r * 0.8, cx + dx * r + r * sc, cy + r * 0.8], fill=color,
                  outline=_rgba(mix(color[:3], (0, 0, 0), 0.25)), width=max(1, int(r * 0.05)))
    d.rounded_rectangle([cx - r * 0.09, cy - r * 1.12, cx + r * 0.09, cy - r * 0.7], radius=r * 0.05, fill=stem)


def bat(d, cx, cy, r, color, ang):
    pts = [(0, -0.15), (0.12, -0.32), (0.16, -0.12), (0.45, -0.35), (0.95, -0.25), (0.8, 0.0),
           (0.62, 0.05), (0.5, 0.25), (0.33, 0.08), (0.15, 0.2), (0, 0.32)]
    full = pts + [(-x, y) for x, y in reversed(pts)]
    d.polygon(_rot([(x * r, y * r) for x, y in full], cx, cy, ang), fill=color)


def cloud(d, cx, cy, r, color):
    for dx, dy, s in ((-0.6, 0.1, 0.45), (0, -0.15, 0.6), (0.6, 0.1, 0.45), (-0.25, 0.2, 0.45), (0.3, 0.2, 0.45)):
        d.ellipse([cx + dx * r - s * r, cy + dy * r - s * r, cx + dx * r + s * r, cy + dy * r + s * r], fill=color)


def confetti_piece(d, cx, cy, r, color, ang, rng):
    kind = rng.random()
    if kind < 0.45:
        pts = _rot([(-r, -r * 0.4), (r, -r * 0.4), (r, r * 0.4), (-r, r * 0.4)], cx, cy, ang)
        d.polygon(pts, fill=color)
    elif kind < 0.8:
        d.ellipse([cx - r * 0.6, cy - r * 0.6, cx + r * 0.6, cy + r * 0.6], fill=color)
    else:
        pts = [(cx + (i - 4) * r * 0.3, cy + math.sin(i * 1.4 + ang) * r * 0.35) for i in range(9)]
        d.line(_rot([(x - cx, y - cy) for x, y in pts], cx, cy, ang), fill=color, width=max(2, int(r * 0.25)))


# ---------------------------------------------------------------- placement
def _inside(x, y, rects, pad):
    return any(r[0] - pad < x < r[2] + pad and r[1] - pad < y < r[3] + pad for r in rects)


def edge_point(rng, w, h, band):
    """Random point biased toward the canvas edges."""
    side = rng.random()
    b = band * min(w, h)
    if side < 0.25:
        return rng.uniform(0, w), rng.uniform(0, b)
    if side < 0.5:
        return rng.uniform(0, w), rng.uniform(h - b, h)
    if side < 0.75:
        return rng.uniform(0, b), rng.uniform(0, h)
    return rng.uniform(w - b, w), rng.uniform(0, h)


def _points(rng, w, h, n, keepout, pad, band=0.2, tries=40):
    pts = []
    for _ in range(n):
        for _ in range(tries):
            x, y = edge_point(rng, w, h, band)
            if not _inside(x, y, keepout, pad):
                pts.append((x, y))
                break
    return pts


def draw_motifs(size, motifs: list[str], pal: Palette, seed: int, keepout: list[Rect] = (),
                density: float = 1.0, ss: int = 2) -> Image.Image:
    """Return an RGBA layer (final size) containing all motifs for a design."""
    W, H = size[0] * ss, size[1] * ss
    keep = [tuple(v * ss for v in r) for r in keepout]
    base = min(W, H)
    scale = base / 1000
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    area_factor = max(0.6, (W * H) / (base * base)) ** 0.5
    cols = [pal.primary, pal.accent, mix(pal.primary, pal.bg, 0.35), mix(pal.accent, (255, 255, 255), 0.3)]

    for m in motifs:
        rng = random.Random(f"{seed}-{m}")
        n_scale = density * area_factor
        if m == "bokeh":
            bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bl)
            for _ in range(int(22 * n_scale)):
                x, y = rng.uniform(0, W), rng.uniform(0, H)
                r = rng.uniform(0.02, 0.08) * base
                c = rng.choice(cols)
                bd.ellipse([x - r, y - r, x + r, y + r], fill=_rgba(c, rng.randint(40, 95)))
            bl = bl.filter(ImageFilter.GaussianBlur(base * 0.006))
            layer.alpha_composite(bl)
            d = ImageDraw.Draw(layer)
        elif m == "confetti":
            for x, y in _points(rng, W, H, int(90 * n_scale), keep, base * 0.01, band=0.22):
                confetti_piece(d, x, y, rng.uniform(0.007, 0.016) * base, _rgba(rng.choice(cols)),
                               rng.uniform(0, math.pi), rng)
        elif m == "sparkle":
            for x, y in _points(rng, W, H, int(26 * n_scale), keep, base * 0.02, band=0.25):
                sparkle(d, x, y, rng.uniform(0.008, 0.028) * base, _rgba(pal.accent, rng.randint(170, 255)),
                        rng.choice([0, math.pi / 4]) if rng.random() < 0.3 else 0)
        elif m == "stars":
            for x, y in _points(rng, W, H, int(30 * n_scale), keep, base * 0.02, band=0.22):
                star(d, x, y, rng.uniform(0.01, 0.03) * base, _rgba(rng.choice([pal.accent, pal.primary])),
                     rng.uniform(-0.4, 0.4))
        elif m == "hearts":
            for x, y in _points(rng, W, H, int(26 * n_scale), keep, base * 0.03, band=0.2):
                heart(d, x, y, rng.uniform(0.012, 0.035) * base, _rgba(rng.choice(cols), rng.randint(190, 255)),
                      rng.uniform(-0.5, 0.5))
        elif m == "snowflakes":
            for x, y in _points(rng, W, H, int(26 * n_scale), keep, base * 0.03, band=0.22):
                c = rng.choice([mix(pal.accent, (255, 255, 255), 0.3), pal.primary, (255, 255, 255)])
                snowflake(d, x, y, rng.uniform(0.015, 0.04) * base, _rgba(c, rng.randint(170, 255)),
                          rng.uniform(0, 1), max(2, int(3 * scale)))
        elif m == "balloons":
            # clusters on left and right sides
            for side in (0, 1):
                cx = W * (0.09 if side == 0 else 0.91)
                for i in range(int(5 * max(1, n_scale * 0.8))):
                    x = cx + rng.uniform(-0.07, 0.07) * base
                    y = rng.uniform(0.08, 0.5) * H
                    if _inside(x, y, keep, base * 0.03):
                        continue
                    balloon(d, x, y, rng.uniform(0.035, 0.06) * base, _rgba(rng.choice(cols)),
                            rng.uniform(0, 6), scale)
        elif m == "botanical":
            green = mix(pal.primary, (110, 140, 100), 0.55)
            green2 = mix(pal.accent, (140, 160, 120), 0.4)
            corners = [(0, 0, math.pi * 0.25), (W, H, math.pi * 1.25), (W, 0, math.pi * 0.75), (0, H, -math.pi * 0.25)]
            for k, (cx, cy, a) in enumerate(corners[: 2 + int(density > 0.9) * 2]):
                for j in range(5):
                    sprig(d, cx, cy, rng.uniform(0.25, 0.42) * base, a + rng.uniform(-0.6, 0.6),
                          _rgba(green if j % 2 else green2), _rgba(mix(green, pal.bg, 0.3)), rng, scale)
        elif m == "pumpkins":
            orange = mix(pal.primary, (235, 120, 30), 0.6)
            for x, y in _points(rng, W, H, int(8 * n_scale), keep, base * 0.06, band=0.14):
                pumpkin(d, x, y, rng.uniform(0.03, 0.06) * base, _rgba(orange), _rgba(mix(pal.accent, (60, 90, 40), 0.5)))
        elif m == "bats":
            for x, y in _points(rng, W, H, int(12 * n_scale), keep, base * 0.04, band=0.25):
                bat(d, x, y, rng.uniform(0.03, 0.06) * base, _rgba(mix(pal.text, (20, 20, 20), 0.5), 230),
                    rng.uniform(-0.3, 0.3))
        elif m == "clouds":
            for x, y in _points(rng, W, H, int(10 * n_scale), keep, base * 0.05, band=0.16):
                cloud(d, x, y, rng.uniform(0.04, 0.08) * base, _rgba(mix(pal.bg, (255, 255, 255), 0.6), 235))
        elif m == "waves":
            for i in range(4):
                c = _rgba(mix(pal.primary, pal.bg, i * 0.22), 230)
                y0 = H * (0.9 + i * 0.025)
                amp, freq = base * 0.012, rng.uniform(2.5, 4.5) * math.pi / W
                ph = rng.uniform(0, 6)
                pts = [(x, y0 + math.sin(x * freq + ph) * amp) for x in range(0, W + 20, 20)]
                d.polygon(pts + [(W, H), (0, H)], fill=c)
        elif m == "geometric":
            lc = _rgba(pal.accent, 200)
            for _ in range(int(14 * n_scale)):
                x, y = edge_point(rng, W, H, 0.18)
                if _inside(x, y, keep, base * 0.04):
                    continue
                r = rng.uniform(0.02, 0.06) * base
                a = rng.uniform(0, math.pi)
                tri = _rot([(0, -r), (r * 0.87, r * 0.5), (-r * 0.87, r * 0.5)], x, y, a)
                d.line(tri + [tri[0]], fill=lc, width=max(2, int(3 * scale)))
            for cx, cy in ((W * 0.06, H * 0.08), (W * 0.94, H * 0.92)):
                for i in range(5):
                    for j in range(5):
                        rr = base * 0.004
                        x, y = cx + (i - 2) * base * 0.022, cy + (j - 2) * base * 0.022
                        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=_rgba(pal.primary, 220))
        elif m == "deco":
            pass  # handled by frame style
    return layer.resize(size, Image.LANCZOS)


def draw_frame(size, style: str, pal: Palette, inset_frac: float = 0.035, ss: int = 2) -> Image.Image:
    W, H = size[0] * ss, size[1] * ss
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if style == "none":
        return layer.resize(size)
    d = ImageDraw.Draw(layer)
    base = min(W, H)
    i1 = base * inset_frac
    i2 = i1 + base * 0.012
    w1 = max(2, int(base * 0.004))
    c = _rgba(pal.accent)
    d.rectangle([i1, i1, W - i1, H - i1], outline=c, width=w1)
    d.rectangle([i2, i2, W - i2, H - i2], outline=_rgba(pal.accent, 160), width=max(1, w1 // 2))
    if style == "deco":
        r = base * 0.09
        for cx, cy, a0 in ((i1, i1, 0), (W - i1, i1, 90), (W - i1, H - i1, 180), (i1, H - i1, 270)):
            for k in range(3):
                rr = r * (1 - k * 0.28)
                d.arc([cx - rr, cy - rr, cx + rr, cy + rr], a0, a0 + 90, fill=c, width=w1)
            for k in range(5):
                a = math.radians(a0 + 9 + k * 18)
                d.line([(cx, cy), (cx + r * math.cos(a), cy + r * math.sin(a))], fill=_rgba(pal.accent, 180), width=max(1, w1 // 2))
    return layer.resize(size, Image.LANCZOS)
