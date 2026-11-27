"""Draft promotional content for TikTok, Instagram and Pinterest.

Everything is written to <bundle>/marketing/ for YOUR review. Nothing here
connects to any social network or posts anything.
"""
from __future__ import annotations

import json
import math
import random
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import render
from .palettes import contrast, mix, smart_title, soft_bg

SANS = ("Montserrat-VF.ttf", "SemiBold")
SANS_B = ("Montserrat-VF.ttf", "ExtraBold")

HOOKS = [
    "POV: your photo booth clients keep asking for {theme_l} designs",
    "Stop designing booth templates at 2am. Here's a {theme_l} set ready to go.",
    "The {theme_l} photo booth bundle your next event needs",
    "Photo booth owners: this {theme_l} set includes {n} colors",
]

HASHTAGS_BASE = ["#photobooth", "#photoboothbusiness", "#photoboothtemplate", "#photoboothrental",
                 "#eventprofs", "#photoboothoverlay", "#smallbusiness"]
CATEGORY_TAGS = {
    "Wedding": ["#weddingphotobooth", "#weddingideas", "#weddinginspo"],
    "Birthday": ["#birthdayparty", "#partyideas", "#birthdayphotobooth"],
    "Holiday": ["#holidayparty", "#christmasparty", "#holidayevents"],
    "New Year": ["#nye", "#newyearseve", "#nyeparty"],
    "Halloween": ["#halloweenparty", "#spookyseason"],
    "Baby Shower": ["#babyshower", "#babyshowerideas"],
    "Graduation": ["#graduationparty", "#classof2027"],
    "Valentine's Day": ["#valentinesday", "#galentines"],
    "Summer": ["#summerparty", "#beachparty"],
    "Corporate Event": ["#corporateevents", "#eventplanning", "#brandactivation"],
    "Party": ["#partyideas", "#eventdecor"],
}


def _cover(img: Image.Image, size) -> Image.Image:
    """Scale/crop to fill size."""
    w, h = size
    s = max(w / img.width, h / img.height)
    im = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _panel(img, box, color, alpha=225, radius=40):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=tuple(color[:3]) + (alpha,))
    img.alpha_composite(layer)


def _badge(img, text, cx, cy, pal, h):
    d = ImageDraw.Draw(img)
    f = render.font(SANS_B, int(h * 0.42))
    tw = d.textlength(text, font=f)
    box = (cx - tw / 2 - h * 0.6, cy - h / 2, cx + tw / 2 + h * 0.6, cy + h / 2)
    d.rounded_rectangle(box, radius=h / 2, fill=tuple(pal.accent) + (255,))
    d.text((cx, cy), text, font=f, fill=tuple(pal.text_on(pal.accent)) + (255,), anchor="mm")


def pinterest_pin(b, previews: dict, out: Path) -> Path:
    pal = b.palettes[0]
    W, H = 1000, 1500
    c = Image.new("RGBA", (W, H), tuple(soft_bg(pal)) + (255,))
    hero = Image.open(previews["hero"]).convert("RGBA")
    hero = hero.crop((0, int(hero.height * 0.17), hero.width, hero.height))  # drop the header text
    c.alpha_composite(_cover(hero, (W, 1000)), dest=(0, 0))
    _panel(c, (40, 930, W - 40, H - 40), soft_bg(pal, 0.7), 250)
    tc = pal.text_on(soft_bg(pal, 0.7))
    render.draw_text_center(c, smart_title(b.job["theme"].strip()), b.profile["title_font"], (80, 960, W - 80, 1150), tc)
    render.draw_text_center(c, "PHOTO BOOTH TEMPLATE BUNDLE", SANS_B, (100, 1170, W - 100, 1230), tc)
    _badge(c, f"{len(b.palettes)} COLORS  •  INSTANT DOWNLOAD", W / 2, 1300, pal, 70)
    render.draw_text_center(c, b.settings["shop_name"], SANS, (200, 1370, W - 200, 1420), mix(tc, (128, 128, 128), 0.3))
    p = out / "pinterest_pin_1000x1500.png"
    c.convert("RGB").save(p, "PNG", optimize=True)
    return p


def instagram_carousel(b, previews: dict, out: Path) -> list[Path]:
    pal = b.palettes[0]
    W, H = 1080, 1350
    slides = []
    theme = smart_title(b.job["theme"].strip())
    # slide 1: hook
    c = _cover(Image.open(previews["hero"]).convert("RGBA"), (W, H)).filter(ImageFilter.GaussianBlur(6))
    _panel(c, (70, 380, W - 70, 970), soft_bg(pal), 235)
    tc = pal.text_on(soft_bg(pal))
    render.draw_text_center(c, "NEW DROP", SANS_B, (150, 420, W - 150, 500), pal.accent if contrast(pal.accent, soft_bg(pal)) > 2.5 else tc)
    render.draw_text_center(c, theme, b.profile["title_font"], (120, 520, W - 120, 740), tc)
    render.draw_text_center(c, "photo booth template bundle", SANS, (150, 760, W - 150, 830), tc)
    render.draw_text_center(c, "swipe  →", SANS_B, (300, 860, W - 300, 920), mix(tc, (128, 128, 128), 0.3))
    slides.append(c)
    # slides 2-4: product images
    for key in ("colors", "prints", "gifbuttons"):
        if key in previews:
            c = Image.new("RGBA", (W, H), tuple(soft_bg(pal)) + (255,))
            im = Image.open(previews[key]).convert("RGBA")
            im.thumbnail((W, H))
            c.alpha_composite(im, dest=((W - im.width) // 2, (H - im.height) // 2))
            slides.append(c)
    # last slide: CTA
    c = Image.new("RGBA", (W, H), tuple(pal.primary) + (255,))
    tc = pal.text_on(pal.primary)
    render.draw_text_center(c, "Ready for your next event?", SANS_B, (100, 420, W - 100, 560), tc)
    render.draw_text_center(c, "Instant download  •  Link in bio", SANS, (140, 600, W - 140, 680), tc)
    render.draw_text_center(c, "Save this post for later", SANS, (240, 760, W - 240, 820), mix(tc, pal.primary, 0.3))
    slides.append(c)
    paths = []
    for i, s in enumerate(slides, 1):
        p = out / f"instagram_carousel_{i}_1080x1350.png"
        s.convert("RGB").save(p, "PNG", optimize=True)
        paths.append(p)
    return paths


def tiktok_video(b, previews: dict, out: Path, fps=30) -> Path:
    """~10s vertical slideshow with slow zoom and on-screen captions."""
    pal = b.palettes[0]
    W, H = 1080, 1920
    scenes = [("hero", "New {theme} photo booth bundle"), ("colors", "{n} color options"),
              ("prints", "Strips + 4x6 overlays"), ("gifbuttons", "GIF overlays + buttons")]
    theme = smart_title(b.job["theme"].strip())
    scenes = [(k, t.format(theme=theme, n=len(b.palettes))) for k, t in scenes if k in previews]
    per = 2.5
    bgc = tuple(soft_bg(pal)) + (255,)
    path = out / "tiktok_reel_1080x1920.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "24",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    tc = pal.text_on(bgc)
    try:
        for key, caption in scenes:
            src = Image.open(previews[key]).convert("RGBA")
            th = int(H * 0.66)
            src = src.resize((int(src.width * th / src.height), th), Image.LANCZOS)
            cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            _panel(cap, (60, 220, W - 60, 470), soft_bg(pal, 0.7), 240)
            render.draw_text_center(cap, caption, SANS_B, (110, 250, W - 110, 440), tc)
            capc = cap.crop((0, 200, W, 500))
            n = int(per * fps)
            for f in range(n):
                # smooth horizontal pan (ease in/out) across the preview
                e = 0.5 - 0.5 * math.cos(math.pi * f / n)
                x = int((src.width - W) * (0.1 + 0.8 * e))
                frame = Image.new("RGBA", (W, H), bgc)
                frame.alpha_composite(src.crop((x, 0, x + W, src.height)), dest=(0, 560))
                frame.alpha_composite(capc, dest=(0, 200))
                proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-400:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return path


def copy_kit(b) -> dict:
    rng = random.Random(b.sku + "mk")
    theme = smart_title(b.job["theme"].strip())
    n = len(b.palettes)
    cat = b.profile["category"]
    tags = HASHTAGS_BASE + CATEGORY_TAGS.get(cat, [])
    theme_tag = "#" + re.sub(r"[^a-z0-9]", "", theme.lower())
    if 3 < len(theme_tag) < 30:
        tags.append(theme_tag)
    hook = rng.choice(HOOKS).format(theme_l=theme.lower(), n=n)
    return {
        "status": "DRAFT - NOT POSTED. Review before publishing.",
        "tiktok": {
            "hook_text": hook,
            "script": [
                f"0-2s  On screen: '{hook}' over the hero mockup.",
                f"2-5s  Show the {n} color variations.",
                "5-7s  Show strips, 4x6 overlays and the GIF overlay.",
                "7-10s End card: 'Instant download - link in bio'.",
            ],
            "caption": f"{hook} ✨ {n} colors, welcome screen, strips, overlays and buttons - instant download. "
                       "Link in bio.",
            "hashtags": tags[:6],
            "sound_note": "Pick a sound from the platform's Commercial Music Library (business accounts) "
                          "to stay license-safe.",
        },
        "instagram": {
            "caption": f"NEW: {smart_title(theme)} photo booth template bundle 📸\n\n"
                       f"✔ {n} color variations\n✔ Welcome screen + animated loop\n✔ 2x6 strips + 4x6 overlays\n"
                       "✔ GIF overlays + experience buttons\n✔ Blank versions to add your clients' names\n\n"
                       "Instant download - link in bio. Save this for your next booking!",
            "hashtags": tags[:15],
            "alt_text": f"Mockup of a {theme.lower()} photo booth template set shown on a tablet with printed photo strips.",
        },
        "pinterest": {
            "title": f"{smart_title(theme)} Photo Booth Template Bundle | {n} Colors"[:100],
            "description": f"Ready-to-use {theme.lower()} photo booth templates for photo booth businesses: "
                           f"welcome screen, animated start screen, 2x6 photo strips, 4x6 overlays, GIF overlays "
                           f"and buttons in {n} colors. Instant digital download.",
            "board_suggestion": f"{cat} Photo Booth Templates",
            "link": "ADD YOUR LISTING URL AFTER YOU PUBLISH",
            "alt_text": f"{theme} photo booth template preview",
        },
        "posting_tips": [
            "Post the TikTok/Reel first; reuse the same video as an Instagram Reel.",
            "Pin the Pinterest image to 2-3 relevant boards over a week rather than all at once.",
            f"Seasonal themes perform best when posted 6-8 weeks before the event season ({cat}).",
        ],
    }


def build_all(b) -> list[Path]:
    out = b.root / "marketing"
    out.mkdir(parents=True, exist_ok=True)
    pv = b.root / "previews"
    previews = {k: pv / f for k, f in (("hero", "01_hero.jpg"), ("colors", "02_color_variations.jpg"),
                                        ("prints", "03_print_templates.jpg"), ("gifbuttons", "04_gif_and_buttons.jpg"))
                if (pv / f).exists()}
    if "hero" not in previews:
        raise RuntimeError("hero preview missing; cannot build marketing images")
    files = [pinterest_pin(b, previews, out)]
    files += instagram_carousel(b, previews, out)
    files.append(tiktok_video(b, previews, out))
    kit = copy_kit(b)
    (out / "captions.json").write_text(json.dumps(kit, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [f"# Marketing kit - {b.sku}", "", f"**{kit['status']}**", ""]
    for net in ("tiktok", "instagram", "pinterest"):
        md.append(f"## {net.title()}")
        for k, v in kit[net].items():
            v = "\n".join(f"- {x}" for x in v) if isinstance(v, list) else v
            md.append(f"**{k.replace('_', ' ').title()}:**\n{v}\n")
    md.append("## Posting tips")
    md += [f"- {t}" for t in kit["posting_tips"]]
    p = out / "captions.md"
    p.write_text("\n".join(md), encoding="utf-8")
    files.append(p)
    return files
