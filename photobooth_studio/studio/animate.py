"""Seamless looping animated welcome screens (H.264 MP4 via ffmpeg).

Static artwork is rendered once; small particle sprites (confetti, snow,
bokeh, sparkles, hearts) move on integer-cycle paths so the last frame flows
perfectly into the first. Frames are piped straight into ffmpeg.
"""
from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import motifs, render
from .palettes import Palette, mix

STATIC = {"botanical", "balloons", "waves", "geometric", "pumpkins", "clouds", "bats", "deco"}
PARTICLES = {"confetti", "sparkle", "stars", "snowflakes", "hearts", "bokeh"}


def _sprite(kind, r, color, seed, pal: Palette):
    s = int(r * 2.6) + 4
    ss = 3
    im = Image.new("RGBA", (s * ss, s * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = s * ss / 2
    R = r * ss
    col = tuple(color[:3]) + (255,)
    rng = random.Random(seed)
    if kind == "confetti":
        motifs.confetti_piece(d, c, c, R, col, rng.uniform(0, math.pi), rng)
    elif kind == "sparkle":
        motifs.sparkle(d, c, c, R, col)
    elif kind == "stars":
        motifs.star(d, c, c, R, col, rng.uniform(-0.4, 0.4))
    elif kind == "snowflakes":
        motifs.snowflake(d, c, c, R, col, rng.uniform(0, 1), max(2, int(R * 0.08)))
    elif kind == "hearts":
        motifs.heart(d, c, c, R, col, rng.uniform(-0.4, 0.4))
    elif kind == "bokeh":
        d.ellipse([c - R, c - R, c + R, c + R], fill=tuple(color[:3]) + (110,))
        im = im.filter(ImageFilter.GaussianBlur(R * 0.12))
    return im.resize((s, s), Image.LANCZOS)


def _alpha_levels(sprite: Image.Image, n=8):
    out = []
    a = sprite.getchannel("A")
    for i in range(n):
        f = (i + 1) / n
        sp = sprite.copy()
        sp.putalpha(a.point(lambda v, f=f: int(v * f)))
        out.append(sp)
    return out


def build_particles(design, pal: Palette, size, frames: int):
    w, h = size
    base = min(w, h)
    kinds = [m for m in design.profile["motifs"] if m in PARTICLES] or ["sparkle", "bokeh"]
    cols = [pal.primary, pal.accent, mix(pal.accent, (255, 255, 255), 0.35)]
    parts = []
    rng = random.Random(f"{design.seed}-anim")
    for kind in kinds:
        n = {"confetti": 55, "sparkle": 22, "stars": 20, "snowflakes": 35, "hearts": 18, "bokeh": 16}[kind]
        n = int(n * max(0.6, (w * h) / (base * base)) ** 0.5)
        for i in range(n):
            r = base * {"confetti": rng.uniform(0.008, 0.015), "bokeh": rng.uniform(0.03, 0.07),
                        "snowflakes": rng.uniform(0.01, 0.025)}.get(kind, rng.uniform(0.01, 0.022))
            spr = _sprite(kind, r, rng.choice(cols), rng.random(), pal)
            parts.append({
                "kind": kind, "levels": _alpha_levels(spr), "x0": rng.uniform(0, w), "y0": rng.uniform(0, h),
                "cycles": rng.choice([1, 1, 2]) if kind in ("confetti", "snowflakes") else 1,
                "sway": rng.uniform(0.005, 0.02) * base, "phase": rng.uniform(0, 2 * math.pi),
                "tw": rng.choice([1, 2, 3]),
            })
    return parts


def _pos(p, t, w, h):
    """t in [0,1). Integer cycles guarantee a seamless loop."""
    sz = p["levels"][0].size[0]
    kind = p["kind"]
    tau = 2 * math.pi * t
    if kind in ("confetti", "snowflakes"):       # fall down
        span = h + sz * 2
        y = (p["y0"] + span * p["cycles"] * t) % span - sz
        x = p["x0"] + math.sin(tau * p["tw"] + p["phase"]) * p["sway"]
        alpha = 1.0
    elif kind in ("bokeh", "hearts"):            # rise up slowly
        span = h + sz * 2
        y = (p["y0"] - span * t) % span - sz
        x = p["x0"] + math.sin(tau + p["phase"]) * p["sway"] * 2
        alpha = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(tau * p["tw"] + p["phase"]))
    else:                                         # twinkle in place
        x, y = p["x0"], p["y0"]
        alpha = max(0.0, math.sin(tau * p["tw"] + p["phase"])) ** 1.5
    return x - sz / 2, y - sz / 2, alpha


def welcome_video(design, pal: Palette, path: Path, size=(1920, 1080), seconds=8, fps=30, crf=23):
    w, h = size
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(seconds * fps)
    # static background (no particle motifs)
    static_design = render.Design(design.theme, dict(design.profile, motifs=[m for m in design.profile["motifs"] if m in STATIC]),
                                  design.seed, design.headline, design.placeholder)
    keep = [(w * 0.18, h * 0.2, w * 0.82, h * 0.86)]
    base = render.compose_base((w, h), static_design, pal, keep)
    text = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    render.welcome_text(text, design, pal, include_cta=False)
    tb = text.getbbox() or (0, 0, 1, 1)
    text_crop = text.crop(tb)
    cta = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    render.cta(cta, pal)
    cb = cta.getbbox() or (0, 0, 1, 1)
    cta_levels = _alpha_levels(cta.crop(cb), 12)
    parts = build_particles(design, pal, (w, h), frames)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(frames):
            t = f / frames
            frame = base.copy()
            for p in parts:
                x, y, a = _pos(p, t, w, h)
                if a <= 0.05:
                    continue
                lvl = p["levels"][min(7, int(a * 8))]
                xi, yi = int(x), int(y)
                if -lvl.size[0] < xi < w and -lvl.size[1] < yi < h:
                    _paste(frame, lvl, xi, yi)
            frame.alpha_composite(text_crop, dest=(tb[0], tb[1]))
            pulse = 0.7 + 0.3 * (0.5 + 0.5 * math.cos(2 * math.pi * t * 2))
            frame.alpha_composite(cta_levels[min(11, int(pulse * 12))], dest=(cb[0], cb[1]))
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-500:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return path


def _paste(frame: Image.Image, sprite: Image.Image, x: int, y: int):
    """alpha_composite that tolerates sprites hanging off the edge."""
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1 = min(sprite.size[0], frame.size[0] - x)
    sy1 = min(sprite.size[1], frame.size[1] - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    frame.alpha_composite(sprite, dest=(x + sx0, y + sy0), source=(sx0, sy0, sx1, sy1))
