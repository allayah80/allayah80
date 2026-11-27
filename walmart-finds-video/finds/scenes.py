"""Scene drawing: hook/intro, product spotlights, CTA, and persistent overlays."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from . import looks as L
from .gfx import (
    H, W, Spr, arrow_up, bezier, circle, clamp, damped, drop_shadow, ease_in_out,
    ease_out_back, ease_out_cubic, ease_out_expo, fit_image, fit_size, lerp, paste,
    place, place_text, prog, rounded, sparkle, stroke_path, text_sprite, text_width,
)

CARD_BOX = (880, 640)          # max product card size
KICKER_Y = 238
NAME_TOP = 292
CONTENT_BOTTOM = 1452          # product content ends above the captions
CAPTION_CY = 1530              # captions sit above the platform UI safe zone
PUSH = 1.05                    # slow push-in zoom over each product scene
SIDE = 60


def money(v):
    return f"${v:,.2f}"


def parse_accent(text):
    """'Walmart finds for *busy* women' -> [(word, accent?)]"""
    out = []
    for tok in text.split():
        acc = tok.startswith("*") or tok.endswith("*") or tok.rstrip(".,!?:").endswith("*")
        out.append((tok.replace("*", ""), acc))
    return out


class Kit:
    """Pre-rendered sprites for one look (cards, tags, chips, thumbnails)."""

    def __init__(self, cfg, look: L.Look):
        self.cfg, self.look = cfg, look
        self.photos = [Image.open(p.image).convert("RGBA") for p in cfg.products]
        self.cards = [self._card(im) for im in self.photos]
        self.thumbs = [self._thumb(im, p) for im, p in zip(self.photos, cfg.products)]
        self.tags = [self._tag(p) for p in cfg.products]
        self.chips = [[self._chip(f) for f in p.features] for p in cfg.products]
        self.disclosure = self._disclosure_card(cfg.disclosure_card)

    # Product card: the photo, uniformly scaled, on a white rounded card.
    def _card(self, photo):
        pad = 34
        img = fit_image(photo, CARD_BOX[0] - 2 * pad, CARD_BOX[1] - 2 * pad)
        cw, ch = img.width + 2 * pad, img.height + 2 * pad
        card = rounded(cw, ch, 42, self.look.card + (255,)).copy()
        card.alpha_composite(img, (pad, pad))
        shadow_col = (0, 0, 0) if self.look.id == "bold" else (90, 60, 50)
        out, spad = drop_shadow(card, blur=30, offset=(0, 22), color=shadow_col,
                                alpha=0.45 if self.look.id == "bold" else 0.2)
        return out, cw, ch

    def _thumb(self, photo, prod, size=300):
        pad = 16
        img = fit_image(photo, size - 2 * pad, size - 2 * pad)
        foot = 64
        card = rounded(size, size + foot, 26, (255, 255, 255, 255)).copy()
        card.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
        s = text_sprite(money(prod.price), "sans_bold", 34, L.INK)
        place_text(card, s, (size - s.w) / 2, size + 2)
        out, _ = drop_shadow(card, blur=18, offset=(0, 12), alpha=0.22)
        return out

    def _tag(self, prod):
        lk = self.look
        dollars, cents = f"{prod.price:.2f}".split(".")
        dollars = f"{int(dollars):,}"
        ink = lk.tag_ink
        if lk.id == "bold":
            # big type price with a blush marker bar
            sd = text_sprite("$", "sans_xbold", 70, lk.ink)
            sn = text_sprite(dollars, "sans_xbold", 168, lk.ink)
            sc = text_sprite("." + cents, "sans_xbold", 70, lk.ink)
            w = sd.w + sn.w + sc.w + 16
            hgt = sn.h + (54 if prod.was_price else 0)
            img = Image.new("RGBA", (w + 40, hgt + 20), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, int(sn.h * 0.52), w + 40, int(sn.h * 0.9)), 10, fill=L.BLUSH_DEEP + (235,))
            x = 20
            place_text(img, sd, x, 22); x += sd.w + 4
            place_text(img, sn, x, 0); x += sn.w + 6
            place_text(img, sc, x, 22)
            if prod.was_price:
                self._was(img, prod.was_price, 20, sn.h + 4, lk.soft_ink, 34)
            return img
        sd = text_sprite("$", "sans_bold", 44, ink)
        sn = text_sprite(dollars, "sans_xbold", 108, ink)
        sc = text_sprite(cents, "sans_bold", 46, ink)
        content = sd.w + 4 + sn.w + 6 + sc.w
        left = 74
        w = left + content + 44
        h = 150 + (50 if prod.was_price else 0)
        s = 3
        big = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        fill = lk.tag_fill + (255,)
        d.rounded_rectangle((40 * s, 0, w * s - 1, h * s - 1), radius=28 * s, fill=fill)
        d.polygon([(0, h * s / 2), (66 * s, 0), (66 * s, h * s)], fill=fill)
        r = 12 * s
        d.ellipse((38 * s - r, h * s / 2 - r, 38 * s + r, h * s / 2 + r), fill=(0, 0, 0, 0))
        img = big.resize((w, h), Image.LANCZOS)
        x, top = left, 18
        place_text(img, sd, x, top + 14); x += sd.w + 4
        place_text(img, sn, x, top - 6); x += sn.w + 6
        place_text(img, sc, x, top + 14)
        if prod.was_price:
            muted = tuple(int(c * 0.75 + (255 if sum(lk.tag_fill) < 300 else 0) * 0.25) for c in ink)
            self._was(img, prod.was_price, left, 140, muted, 30)
        out, _ = drop_shadow(img, blur=16, offset=(0, 10), alpha=0.28)
        return out

    @staticmethod
    def _was(img, was, x, y, color, size):
        lab = text_sprite("was", "sans_medium", size, color)
        val = text_sprite(money(was), "sans_semibold", size, color)
        place_text(img, lab, x, y)
        vx = x + lab.w + 10
        place_text(img, val, vx, y)
        d = ImageDraw.Draw(img)
        ly = y + val.h * 0.55
        d.line((vx - 2, ly, vx + val.w + 2, ly), fill=color + (255,), width=3)

    def _chip(self, text):
        lk = self.look
        s = text_sprite(text, "sans_semibold", 28, lk.chip_ink)
        h = 62
        w = s.w + 56 + 22
        if lk.chip_fill:
            base = rounded(w, h, h // 2, lk.chip_fill + (255,)).copy()
        else:
            base = rounded(w, h, h // 2, (0, 0, 0, 0), outline=lk.chip_line + (255,), width=2).copy()
        dot = circle(14, lk.accent + (255,))
        base.alpha_composite(dot, (28, (h - 14) // 2))
        place_text(base, s, 28 + 14 + 14, (h - s.h) / 2)
        return base

    def _disclosure_card(self, text):
        lk = self.look
        fill = L.CREAM if lk.id == "bold" else (255, 255, 255)
        w = 920
        key, size = "sans_medium", 34
        from .gfx import wrap_words
        lines = wrap_words(text.split(), key, size, w - 100)
        lh = 46
        h = 100 + lh * len(lines) + 20
        card = rounded(w, h, 34, fill + (255,)).copy()
        k = text_sprite("AFFILIATE DISCLOSURE", "sans_bold", 24, L.BLUSH_DEEP, tracking=3)
        place_text(card, k, 50, 40)
        for i, ln in enumerate(lines):
            s = text_sprite(" ".join(ln), key, size, L.INK)
            place_text(card, s, 50, 84 + i * lh)
        out, _ = drop_shadow(card, blur=22, offset=(0, 14), alpha=0.25)
        return out


# --------------------------------------------------------------- headline --

def kinetic(layer, words, key, size, color, accent, cx, top, u, start, *,
            max_w=920, max_lines=3, stagger=0.07, style="rise", line_h=1.08,
            accent_key=None, upper=False, dur=0.5):
    """Animated, centered, word-by-word headline. Returns (bottom_y, accent_boxes)."""
    words = [((w.upper() if upper else w), a) for w, a in words]
    size, lines = fit_size([w for w, _ in words], key, size, max_w, max_lines)
    acc_map = {}
    idx = 0
    flat = []
    for li, ln in enumerate(lines):
        for w in ln:
            flat.append((li, w, words[idx][1]))
            idx += 1
    space = text_width(" ", key, size)
    lh = size * line_h
    boxes = []
    i = 0
    for li, ln in enumerate(lines):
        items = [(w, a) for (l2, w, a) in flat if l2 == li]
        sprites = []
        for w, a in items:
            k = (accent_key or key) if a else key
            sprites.append((text_sprite(w, k, size, accent if a else color), a))
        lw = sum(s.w for s, _ in sprites) + space * (len(sprites) - 1)
        x = cx - lw / 2
        y = top + li * lh
        for s, a in sprites:
            p = prog(u, start + i * stagger, dur)
            if style == "rise":
                e = ease_out_cubic(p)
                place_text(layer, s, x, y + 46 * (1 - e), opacity=clamp(p * 1.8))
            elif style == "pop":
                e = ease_out_back(p, 2.2)
                place_text(layer, s, x, y + 18 * (1 - p), opacity=clamp(p * 2.5), scale=max(0.02, lerp(0.55, 1, e)))
            elif style == "slam":
                e = ease_out_expo(p)
                place_text(layer, s, x, y, opacity=clamp(p * 4), scale=lerp(1.9, 1, e))
            if a:
                boxes.append((x, y, s.w, s.h, start + i * stagger))
            x += s.w + space
            i += 1
    from .gfx import font as _font
    asc, desc = _font(key, size).getmetrics()
    return top + (len(lines) - 1) * lh + asc + desc * 0.6, boxes, size


def swoosh(layer, x, y, w, p, color, width=9):
    pts = bezier((x - 6, y + 6), (x + w * 0.3, y - 10), (x + w * 0.7, y + 14), (x + w + 8, y - 4))
    stroke_path(layer, pts, ease_in_out(p), color + (255,), width)


def marker(layer, x, y, w, h, p, color):
    """Highlighter bar drawn behind a word, left to right."""
    if p <= 0:
        return
    ww = int(w * ease_out_cubic(p)) + 16
    bar = rounded(max(ww, 4), int(h * 0.42), 8, color + (255,))
    paste(layer, bar, x - 8, y + h * 0.55)


# ---------------------------------------------------------------- scenes ---

class Scenes:
    def __init__(self, cfg, look: L.Look, kit: Kit, tl):
        self.cfg, self.look, self.kit, self.tl = cfg, look, kit, tl
        self._layouts = {}

    # ---------------------------------------------------------- intro ----
    def intro(self, layer, u, variation):
        lk = self.look
        cfg = self.cfg
        hook = parse_accent(cfg.fill(variation.hook))
        kicker = cfg.fill(variation.kicker)
        disc_u = self.tl.disclosure_at
        real_u = u
        u = u + 0.35  # pre-roll: frame 0 already shows the hook mid-motion

        if lk.id == "editorial":
            self._fan(layer, u, cy=1120, spread=270, start=0.0)
            if kicker:
                self._kicker_pill(layer, kicker, 370, u, 0.05)
            bottom, boxes, _ = kinetic(layer, hook, "serif", 118, lk.ink, lk.accent, W / 2, 450, u, 0.1,
                                       stagger=0.075, accent_key="serif_italic", max_lines=3)
            for (x, y, w, h, st) in boxes[:1]:
                swoosh(layer, x, y + h * 0.98, w, prog(u, st + 0.55, 0.6), lk.accent)
            for k, (sx, sy, sz) in enumerate([(150, 380, 46), (930, 470, 34), (900, 300, 24)]):
                tw = 0.6 + 0.4 * math.sin(u * 3 + k * 2)
                place(layer, sparkle(sz, lk.accent + (255,)), sx, sy, scale=ease_out_back(prog(u, 0.5 + k * 0.15, 0.5)) * tw)
        elif lk.id == "checklist":
            if kicker:
                self._kicker_pill(layer, kicker, 330, u, -0.1)
            bottom, boxes, size = kinetic(layer, hook, "sans_xbold", 108, lk.ink, lk.ink, W / 2, 410, u, -0.05,
                                          stagger=0.07, style="pop", max_lines=3)
            self._checklist_rows(layer, u, top=max(bottom + 90, 860))
        else:  # bold
            shake = 7 * damped(prog(u, 0.0, 1.2), 5, 6)
            bottom, boxes, _ = kinetic(layer, hook, "sans_xbold", 128, lk.ink, lk.accent, W / 2 + shake, 330, u, -0.12,
                                       stagger=0.17, style="slam", max_lines=4, upper=True, dur=0.28, line_h=1.0)
            if kicker:
                s = text_sprite(kicker, "serif_italic", 60, lk.accent)
                p = prog(u, 1.0, 0.5)
                place_text(layer, s, W / 2 - s.w / 2, bottom + 30 + 30 * (1 - ease_out_cubic(p)), opacity=p)
            self._fly_in(layer, u, cy=min(max(bottom + 330, 1080), 1190))

        # disclosure card slides up when the disclosure slot starts
        if real_u >= disc_u - 0.05:
            p = ease_out_back(prog(real_u, disc_u, 0.55), 1.2)
            card = self.kit.disclosure
            place(layer, card, W / 2, 1530 + 380 * (1 - p), opacity=clamp(prog(real_u, disc_u, 0.3)))

    def _kicker_pill(self, layer, text, y, u, start):
        lk = self.look
        s = text_sprite(text.upper(), "sans_bold", 28, lk.pill_ink, tracking=3)
        pill = rounded(s.w + 64, 62, 31, lk.pill_fill + (255,)).copy()
        place_text(pill, s, 32, (62 - s.h) / 2)
        p = prog(u, start, 0.45)
        place(layer, pill, W / 2, y, scale=max(0.02, ease_out_back(p, 2)), opacity=clamp(p * 3))

    def _fan(self, layer, u, cy, spread, start):
        n = len(self.kit.thumbs)
        p = ease_out_back(prog(u, start, 0.8), 1.3)
        mid = (n - 1) / 2
        for i, th in enumerate(self.kit.thumbs):
            off = (i - mid)
            x = W / 2 + off * spread * p
            rot = -off * 8 * p
            y = cy + abs(off) * 40 * p + 8 * math.sin(u * 1.6 + i)
            sc = lerp(1.15, 0.98 if n > 2 else 1.05, ease_out_cubic(prog(u, start, 0.8)))
            place(layer, th, x, y, scale=sc, rot=rot)

    def _fly_in(self, layer, u, cy):
        n = len(self.kit.thumbs)
        mid = (n - 1) / 2
        for i, th in enumerate(self.kit.thumbs):
            off = i - mid
            p = prog(u, 0.35 + 0.18 * i, 0.55)
            e = ease_out_back(p, 1.6)
            side = -1 if i % 2 == 0 else 1
            x = W / 2 + off * 280 + side * 700 * (1 - e)
            y = cy + abs(off) * 50 + 10 * math.sin(u * 2 + i)
            place(layer, th, x, y, scale=0.86, rot=lerp(side * 25, -off * 6, e), opacity=clamp(p * 3))

    def _checklist_rows(self, layer, u, top):
        lk = self.look
        n = len(self.cfg.products)
        row_h, gap = 150, 26
        for i, prod in enumerate(self.cfg.products):
            p = prog(u, 0.25 + 0.16 * i, 0.5)
            if p <= 0:
                continue
            e = ease_out_cubic(p)
            row = rounded(940, row_h, 30, (255, 255, 255, 255)).copy()
            # checkbox
            box = rounded(56, 56, 14, (0, 0, 0, 0), outline=lk.ink + (255,), width=3)
            row.alpha_composite(box, (30, (row_h - 56) // 2))
            th = fit_image(self.kit.photos[i], 118, 118)
            row.alpha_composite(th, (112 + (118 - th.width) // 2, (row_h - th.height) // 2))
            name = text_sprite(prod.short_name, "sans_bold", 40, lk.ink)
            if name.w > 470:
                name = text_sprite(prod.short_name, "sans_bold", 32, lk.ink)
            place_text(row, name, 260, (row_h - name.h) / 2)
            price = text_sprite(money(prod.price), "sans_xbold", 42, lk.ink)
            place_text(row, price, 940 - 34 - price.w, (row_h - price.h) / 2)
            ck = prog(u, 0.7 + 0.22 * i, 0.35)
            if ck > 0:
                stroke_path(row, [(42, 76), (56, 92), (86, 56)], ck, L.BLUSH_DEEP + (255,), 9)
            y = top + i * (row_h + gap) + row_h / 2
            place(layer, row, W / 2 + 500 * (1 - e), y, opacity=clamp(p * 2))

    # -------------------------------------------------------- product ----
    def _name(self, layer, u, prod):
        lk = self.look
        words = [(w, False) for w in prod.short_name.split()]
        if lk.id == "editorial":
            return kinetic(layer, words, "serif", 96, lk.ink, lk.accent, W / 2, NAME_TOP, u, 0.12,
                           max_lines=2, max_w=900)[0]
        if lk.id == "checklist":
            return kinetic(layer, words, "sans_xbold", 84, lk.ink, lk.ink, W / 2, NAME_TOP, u, 0.1,
                           max_lines=2, max_w=900, style="pop", stagger=0.06)[0]
        return kinetic(layer, words, "sans_xbold", 88, lk.ink, lk.accent, W / 2, NAME_TOP - 4, u, 0.08,
                       max_lines=2, max_w=920, style="slam", stagger=0.12, upper=True, dur=0.26, line_h=1.0)[0]

    def _chip_rows(self, i):
        rows, cur, cur_w = [], [], 0
        for c in self.kit.chips[i]:
            if cur and cur_w + 14 + c.width > 960:
                rows.append(cur); cur, cur_w = [], 0
            cur.append(c); cur_w += c.width + (14 if cur_w else 0)
        if cur:
            rows.append(cur)
        return rows

    def _layout(self, i):
        """Vertical stack: name, card, price, note, chips - all above the captions.
        The card is scaled down (uniformly) if needed so nothing overlaps the photo."""
        if i in self._layouts:
            return self._layouts[i]
        tmp = Image.new("RGBA", (W, H))
        name_bottom = self._name(tmp, 99, self.cfg.products[i])
        _, cw, ch = self.kit.cards[i]
        tag = self.kit.tags[i]
        overlap = 0 if self.look.id == "bold" else 34      # tag may overlap the card's padding only
        rows = self._chip_rows(i)
        below = tag.height - 2 * 26 - overlap + 14 + 30 + (18 + 76 * len(rows) if rows else 0)
        card_top = name_bottom + 92
        avail = CONTENT_BOTTOM - below - card_top
        scale = min(1.0, avail / (ch * PUSH))
        cy = card_top + ch * scale / 2 + max(0, (avail - ch * scale * PUSH)) * 0.35
        self._layouts[i] = (name_bottom, scale, cy, rows, overlap)
        return self._layouts[i]

    def product(self, layer, u, i, dur):
        lk = self.look
        prod = self.cfg.products[i]
        n = len(self.cfg.products)
        name_bottom, cscale, cy, rows, overlap = self._layout(i)

        # kicker: 01 / 03 · CATEGORY   (checklist: progress boxes instead of numbers)
        kp = prog(u, 0.05, 0.4)
        ky = KICKER_Y + 20 * (1 - ease_out_cubic(kp))
        if lk.id == "checklist":
            ks = text_sprite(prod.category.upper(), "sans_bold", 28, L.BLUSH_DEEP, tracking=3)
            bw = n * 34 + (n - 1) * 12
            x0 = W / 2 - (bw + 24 + ks.w) / 2
            self._progress_boxes(layer, u, i, n, x0, ky + ks.h / 2)
            place_text(layer, ks, x0 + bw + 24, ky, opacity=kp)
        else:
            kick = f"{i + 1:02d} / {n:02d}" + (f"  ·  {prod.category.upper()}" if prod.category else "")
            ks = text_sprite(kick, "sans_bold", 28, lk.soft_ink, tracking=3)
            place_text(layer, ks, W / 2 - ks.w / 2, ky, opacity=kp)

        self._name(layer, u, prod)
        full = text_sprite(prod.name if len(prod.name) <= 60 else prod.name[:57].rsplit(" ", 1)[0] + "…",
                           "sans_medium", 26, lk.soft_ink)
        place_text(layer, full, W / 2 - full.w / 2, name_bottom + 8, opacity=prog(u, 0.45, 0.4))

        # product card: pop in, then a slow continuous push-in (uniform scale only)
        card, cw, ch = self.kit.cards[i]
        pin = prog(u, 0.15, 0.65)
        enter = lerp(0.86, 1.0, ease_out_back(pin, 1.4))
        push = 1 + (PUSH - 1) * ease_in_out(clamp(u / max(dur, 1)))
        floaty = 5 * math.sin(u * 1.4)
        s = cscale * enter * push
        place(layer, card, W / 2, cy + floaty + 60 * (1 - ease_out_cubic(pin)), scale=s, opacity=clamp(pin * 2.5))
        card_bottom = cy + ch * cscale * PUSH / 2

        # animated price, centered under the card
        tag = self.kit.tags[i]
        tag_top = card_bottom - overlap - 26
        tp = prog(u, 0.75, 0.6)
        if tp > 0:
            tcy = tag_top + tag.height / 2
            if lk.id == "bold":
                e = ease_out_expo(tp)
                place(layer, tag, W / 2, tcy, scale=lerp(1.6, 1, e), opacity=clamp(tp * 3))
            else:
                swing = -3 + 10 * damped(tp, 1.6, 3.2)
                place(layer, tag, W / 2, tcy, scale=max(0.02, ease_out_back(clamp(tp * 1.6), 2.0)), rot=swing)

        # verified-price note
        note_y = tag_top + tag.height - 26 + 14
        note = self.cfg.price_note.format(date=prod.verified_on.strftime("%b %-d, %Y"))
        ns = text_sprite(note, "sans_medium", 22, lk.soft_ink)
        place_text(layer, ns, W / 2 - ns.w / 2, note_y, opacity=prog(u, 1.0, 0.4) * 0.9)

        # feature chips (only facts from the product listing)
        y = note_y + 30 + 18
        k = 0
        for row in rows:
            rw = sum(c.width for c in row) + 14 * (len(row) - 1)
            x = W / 2 - rw / 2
            for c in row:
                p = prog(u, 1.15 + 0.14 * k, 0.45)
                e = ease_out_back(p, 1.5)
                paste(layer, c, x - 40 * (1 - e), y, opacity=clamp(p * 2))
                x += c.width + 14
                k += 1
            y += 76

    def _progress_boxes(self, layer, u, i, n, x0, y):
        lk = self.look
        size, gap = 34, 12
        for k in range(n):
            x = x0 + k * (size + gap)
            done = k < i or (k == i and u > 0.9)
            box = rounded(size, size, 9, (L.BLACK + (255,)) if done else (0, 0, 0, 0),
                          outline=lk.ink + (255,), width=3)
            paste(layer, box, x, y - size / 2)
            if done:
                p = 1.0 if k < i else prog(u, 0.9, 0.3)
                stroke_path(layer, [(x + 8, y + 1), (x + 15, y + 8), (x + 27, y - 7)], p, L.CREAM + (255,), 5)

    # ------------------------------------------------------------ cta ----
    def cta(self, layer, u):
        lk = self.look
        cfg = self.cfg
        n = len(self.kit.thumbs)
        # recap row of products with their verified prices
        spacing = min(320, 960 / n)
        sc = min(0.9, spacing / 330)
        for i, th in enumerate(self.kit.thumbs):
            p = prog(u, 0.05 + 0.1 * i, 0.5)
            x = W / 2 + (i - (n - 1) / 2) * spacing
            place(layer, th, x, 560 + 40 * (1 - ease_out_cubic(p)) + 6 * math.sin(u * 2 + i),
                  scale=sc * lerp(0.7, 1, ease_out_back(p)), rot=(i - (n - 1) / 2) * -4, opacity=clamp(p * 2))

        text = cfg.cta
        if "—" in text:
            a, b = text.split("—", 1)
            words = [(w, False) for w in (a.strip() + " —").split()] + [(w, True) for w in b.split()]
        else:
            words = [(w, False) for w in text.split()]
        if lk.id == "editorial":
            bottom, boxes, _ = kinetic(layer, words, "serif", 104, lk.ink, lk.accent, W / 2, 860, u, 0.25,
                                       accent_key="serif_italic", max_lines=3)
        elif lk.id == "checklist":
            bottom, boxes, _ = kinetic(layer, words, "sans_xbold", 92, lk.ink, L.BLUSH_DEEP, W / 2, 860, u, 0.2,
                                       style="pop", max_lines=3)
        else:
            bottom, boxes, _ = kinetic(layer, words, "sans_xbold", 100, lk.ink, lk.accent, W / 2, 850, u, 0.15,
                                       style="slam", stagger=0.12, upper=True, dur=0.26, max_lines=4, line_h=1.0)
        if boxes:
            x0 = boxes[0][0]
            y0 = boxes[0][1]
            same = [b for b in boxes if abs(b[1] - y0) < 2]
            x1 = same[-1][0] + same[-1][2]
            swoosh(layer, x0, y0 + boxes[0][3] * 1.0, x1 - x0, prog(u, boxes[-1][4] + 0.3, 0.6), lk.accent)

        # bouncing arrow toward the profile/bio + handle
        ap = prog(u, 0.9, 0.4)
        bounce = 14 * abs(math.sin(u * 4.2))
        place(layer, arrow_up(56, 84, lk.ink + (255,), 9), W / 2, bottom + 110 - bounce, opacity=ap)
        hs = text_sprite(cfg.handle, "sans_bold", 40, lk.pill_ink)
        pill = rounded(hs.w + 70, 78, 39, lk.pill_fill + (255,)).copy()
        place_text(pill, hs, 35, (78 - hs.h) / 2)
        hp = prog(u, 1.05, 0.45)
        place(layer, pill, W / 2, bottom + 230, scale=max(0.02, ease_out_back(hp, 2)), opacity=clamp(hp * 3))
        ds = text_sprite(cfg.disclosure_pill, "sans_medium", 26, lk.soft_ink)
        place_text(layer, ds, W / 2 - ds.w / 2, bottom + 300, opacity=prog(u, 1.3, 0.4))

    # ------------------------------------------------------- overlays ----
    def overlays(self, frame, t, ai_used):
        lk = self.look
        # always-visible affiliate disclosure
        s = text_sprite(self.cfg.disclosure_pill, "sans_semibold", 25, lk.pill_ink)
        pill = rounded(s.w + 44, 50, 25, lk.pill_fill + (235,)).copy()
        place_text(pill, s, 22, (50 - s.h) / 2)
        paste(frame, pill, SIDE - 10, 112)
        hs = text_sprite(self.cfg.handle, "sans_semibold", 25, lk.soft_ink)
        place_text(frame, hs, W - SIDE - hs.w, 124)
        if ai_used:
            a = text_sprite(self.cfg.ai_label, "sans_medium", 21, lk.soft_ink)
            lab = rounded(a.w + 32, 36, 18, (lk.pill_fill + (170,))).copy()
            place_text(lab, a, 16, (36 - a.h) / 2)
            paste(frame, lab, SIDE - 10, 172)
        self._captions(frame, t)

    def _captions(self, frame, t):
        lk = self.look
        chunk = None
        for c in self.tl.chunks:
            if c.start <= t < c.end:
                chunk = c
                break
        if chunk is None:
            return
        key, size = "sans_bold", 50
        upper = lk.id == "bold"
        toks = [(w.text.upper() if upper else w.text) for w in chunk.words]
        sprites = [text_sprite(x, key, size, lk.cap_ink) for x in toks]
        space = text_width(" ", key, size)
        lines, cur, cw = [], [], 0
        for k, s in enumerate(sprites):
            if cur and cw + space + s.w > 880:
                lines.append(cur); cur, cw = [], 0
            cw = cw + space + s.w if cur else s.w
            cur.append(k)
        lines.append(cur)
        lh = 72
        widths = [sum(sprites[k].w for k in ln) + space * (len(ln) - 1) for ln in lines]
        bw = max(widths) + 64
        bh = lh * len(lines) + 30
        box = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
        box.alpha_composite(rounded(int(bw), int(bh), 26, lk.cap_fill + (238,)))
        for li, ln in enumerate(lines):
            x = (bw - widths[li]) / 2
            y = 15 + li * lh + (lh - sprites[ln[0]].h) / 2
            for k in ln:
                s = sprites[k]
                w = chunk.words[k]
                active = w.start <= t < (chunk.words[k + 1].start if k + 1 < len(chunk.words) else chunk.end)
                if active:
                    hi = rounded(s.w + 20, s.h + 6, 12, lk.cap_hi_fill + (255,))
                    paste(box, hi, x - 10, y - 3)
                    s = text_sprite(toks[k], key, size, lk.cap_hi_ink)
                place_text(box, s, x, y)
                x += s.w + space
        p = prog(t, chunk.start, 0.14)
        place(frame, box, W / 2, CAPTION_CY, scale=lerp(0.92, 1, ease_out_back(p, 2)), opacity=clamp(p * 3))
