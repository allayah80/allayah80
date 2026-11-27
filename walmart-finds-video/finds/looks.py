"""The three visual styles, their backgrounds and their scene transitions.

Palette: cream, blush, beige and black.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .gfx import H, W, ease_in_out, ease_out_cubic, ease_in_cubic, clamp, paste

CREAM = (246, 240, 232)
CREAM_LIGHT = (251, 247, 242)
BEIGE = (226, 210, 192)
BEIGE_DARK = (196, 174, 152)
BLUSH = (236, 200, 193)
BLUSH_LIGHT = (245, 224, 219)
BLUSH_DEEP = (205, 146, 140)
BLACK = (22, 19, 18)
INK = (30, 25, 23)
MUTED = (122, 108, 98)
WHITE = (255, 255, 255)


@dataclass
class Look:
    id: str
    bg_top: tuple
    bg_bottom: tuple
    blobs: list            # (color, cx, cy, radius, alpha)
    ink: tuple             # main text
    soft_ink: tuple        # secondary text
    accent: tuple          # blush accent
    card: tuple
    tag_fill: tuple
    tag_ink: tuple
    chip_fill: tuple | None
    chip_line: tuple | None
    chip_ink: tuple
    pill_fill: tuple
    pill_ink: tuple
    cap_fill: tuple        # caption box
    cap_ink: tuple
    cap_hi_fill: tuple     # highlighted word box
    cap_hi_ink: tuple
    headline_font: str
    headline_upper: bool
    transition: str        # rise | wipe | whip
    wipe_color: tuple = BEIGE


LOOKS = {
    # 1. Editorial: cream paper, serif headlines, soft rise transitions
    "editorial": Look(
        id="editorial",
        bg_top=CREAM_LIGHT, bg_bottom=(240, 229, 216),
        blobs=[(BLUSH, 0.95, 0.12, 420, 0.55), (BEIGE, 0.05, 0.62, 480, 0.6),
               (BLUSH_LIGHT, 0.8, 0.92, 380, 0.7)],
        ink=INK, soft_ink=MUTED, accent=BLUSH_DEEP, card=WHITE,
        tag_fill=BLUSH, tag_ink=INK, chip_fill=WHITE, chip_line=None, chip_ink=INK,
        pill_fill=(255, 255, 255), pill_ink=INK,
        cap_fill=(255, 255, 255), cap_ink=INK, cap_hi_fill=BLUSH, cap_hi_ink=INK,
        headline_font="serif", headline_upper=False, transition="rise",
    ),
    # 2. Checklist: blush, numbered list energy, beige panel wipes
    "checklist": Look(
        id="checklist",
        bg_top=(247, 228, 223), bg_bottom=(242, 233, 224),
        blobs=[(WHITE, 0.15, 0.1, 420, 0.55), (BLUSH, 0.9, 0.55, 460, 0.6),
               (BEIGE, 0.2, 0.95, 420, 0.55)],
        ink=INK, soft_ink=(128, 104, 98), accent=BLUSH_DEEP, card=WHITE,
        tag_fill=BLACK, tag_ink=CREAM, chip_fill=None, chip_line=INK, chip_ink=INK,
        pill_fill=BLACK, pill_ink=CREAM,
        cap_fill=BLACK, cap_ink=CREAM, cap_hi_fill=BLUSH, cap_hi_ink=INK,
        headline_font="sans_xbold", headline_upper=False, transition="wipe",
        wipe_color=BEIGE,
    ),
    # 3. Bold: black with cream type, price-first, whip pans
    "bold": Look(
        id="bold",
        bg_top=(24, 21, 20), bg_bottom=(38, 32, 29),
        blobs=[(BLUSH_DEEP, 0.85, 0.18, 460, 0.28), (BEIGE_DARK, 0.1, 0.75, 520, 0.18)],
        ink=CREAM, soft_ink=(196, 182, 168), accent=BLUSH, card=WHITE,
        tag_fill=CREAM, tag_ink=BLACK, chip_fill=None, chip_line=CREAM, chip_ink=CREAM,
        pill_fill=CREAM, pill_ink=BLACK,
        cap_fill=CREAM, cap_ink=BLACK, cap_hi_fill=BLUSH, cap_hi_ink=BLACK,
        headline_font="sans_xbold", headline_upper=True, transition="whip",
    ),
}

DRIFT = 60  # px of slow background parallax


def make_background(look: Look, ai_image=None, seed=7):
    """Background plate slightly larger than the frame so it can drift.

    If an AI-generated image is supplied it is cover-fitted and washed with the
    look's palette so it stays on-brand; the renderer adds a visible label.
    """
    bw, bh = W + 2 * DRIFT, H + 2 * DRIFT
    y = np.linspace(0, 1, bh)[:, None, None]
    top = np.array(look.bg_top, float)[None, None, :]
    bot = np.array(look.bg_bottom, float)[None, None, :]
    arr = np.repeat(top * (1 - y) + bot * y, bw, axis=1)

    if ai_image is not None:
        ai = ImageOps.fit(Image.open(ai_image).convert("RGB"), (bw, bh), Image.LANCZOS)
        a = np.asarray(ai, float)
        arr = a * 0.62 + arr * 0.38
    else:
        # soft blush/beige light blobs, rendered small then upscaled (fast + smooth)
        q = 8
        small = Image.fromarray(arr[::q, ::q].astype(np.uint8)).convert("RGBA")
        for color, fx, fy, r, alpha in look.blobs:
            layer = Image.new("RGBA", small.size, color + (0,))
            from PIL import ImageDraw
            d = ImageDraw.Draw(layer)
            cx, cy, rr = fx * bw / q, fy * bh / q, r / q
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=color + (int(255 * alpha),))
            layer = layer.filter(ImageFilter.GaussianBlur(rr * 0.6))
            small.alpha_composite(layer)
        arr = np.asarray(small.convert("RGB").resize((bw, bh), Image.BICUBIC), float)

    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 3.2, (bh, bw, 1))
    arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("RGBA")


def background_frame(plate, t):
    ox = DRIFT + DRIFT * 0.7 * math.sin(t * 0.21)
    oy = DRIFT + DRIFT * 0.7 * math.cos(t * 0.17)
    return plate.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))


# ------------------------------------------------------------ transitions --

def _shifted(layer, dx, dy, opacity=1.0):
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paste(out, layer, dx, dy, opacity)
    return out


def transition(look: Look, frame, A, B, p, label=None):
    """Composite outgoing layer A and incoming layer B onto frame (RGBA)."""
    if look.transition == "rise":
        e = ease_in_out(p)
        paste(frame, A, 0, -110 * ease_in_cubic(clamp(p * 2.2)), 1 - clamp(p * 2.4))
        paste(frame, B, 0, 160 * (1 - ease_out_cubic(clamp((p - 0.3) / 0.7))), clamp((p - 0.3) / 0.4))
        return frame

    if look.transition == "wipe":
        from PIL import ImageDraw
        if p < 0.5:
            frame.alpha_composite(A)
            e = ease_in_out(p / 0.5)
            top = int(H * (1 - e))
            panel_top, panel_bot = top, H
        else:
            frame.alpha_composite(B)
            e = ease_in_out((p - 0.5) / 0.5)
            panel_top, panel_bot = 0, int(H * (1 - e))
        if panel_bot - panel_top > 0:
            d = ImageDraw.Draw(frame)
            d.rectangle((0, panel_top, W, panel_bot), fill=look.wipe_color + (255,))
            # thin blush leading edge
            edge = panel_top if p < 0.5 else panel_bot
            d.rectangle((0, edge - 7, W, edge + 7), fill=BLUSH + (255,))
            if label is not None and panel_bot - panel_top > 500:
                cy = (panel_top + panel_bot) / 2
                paste(frame, label, (W - label.width) / 2, cy - label.height / 2)
        return frame

    if look.transition == "whip":
        e = ease_in_out(p)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        paste(layer, A, -W * e, 0)
        paste(layer, B, W * (1 - e), 0)
        blur = math.sin(math.pi * p)
        if blur > 0.08:
            k = 1 + 10 * blur  # horizontal motion smear
            small = layer.resize((max(8, int(W / k)), H), Image.BILINEAR)
            layer = small.resize((W, H), Image.BILINEAR)
        frame.alpha_composite(layer)
        return frame

    raise ValueError(look.transition)
