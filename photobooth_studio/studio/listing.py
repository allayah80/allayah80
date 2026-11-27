"""Product titles, descriptions, tags and suggested prices.

Template based and deterministic (seeded by the SKU), so it costs nothing to
run. Every output is checked against the trademark blocklist by validate.py.
"""
from __future__ import annotations

import math
import random
import re

from .config import PRODUCT_SPECS, load_settings
from . import db

TYPE_NOUNS = {
    "welcome_screen": "Welcome Screen",
    "welcome_video": "Animated Welcome Screen",
    "strip_2x6": "2x6 Photo Strip",
    "overlay_4x6": "4x6 Overlay",
    "gif_overlay": "GIF Overlay",
    "buttons": "Booth Buttons",
}

TYPE_TAGS = {
    "welcome_screen": ["welcome screen", "booth start screen"],
    "welcome_video": ["animated welcome", "booth video screen"],
    "strip_2x6": ["2x6 photo strip", "photo strip template"],
    "overlay_4x6": ["4x6 overlay", "4x6 photo template"],
    "gif_overlay": ["gif overlay", "boomerang overlay"],
    "buttons": ["booth buttons", "photo booth icons"],
}

BASE_TAGS = ["photo booth template", "photobooth overlay", "photo booth design",
             "booth business", "instant download", "event template"]

INTROS = [
    "Give every guest a moment to remember with this {theme_l} photo booth collection.",
    "Elevate your next event with a polished, ready-to-use {theme_l} photo booth design set.",
    "Set the mood from the very first tap with this coordinated {theme_l} photo booth bundle.",
]


def _title_case(s):
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in s.split())


def price_for(product_types, n_variations, category=None) -> dict:
    st = load_settings()
    pr = st["pricing"]
    comps = sum(pr["component_prices"].get(t, 3.0) for t in product_types)
    if len(product_types) > 1:
        comps *= pr["bundle_discount"]
    comps *= 1 + pr["extra_variation_uplift"] * max(0, n_variations - 1)
    rationale = [f"component value after bundle discount and {n_variations} color variations"]
    # Use real sales data (if any) for the same category to nudge the price.
    hist = None
    if category:
        hist = db.one("SELECT AVG(s.revenue / MAX(s.quantity,1)) AS avg_price, COUNT(*) AS n FROM sales s "
                      "JOIN products p ON p.sku = s.sku WHERE p.category = ?", (category,))
    if hist and hist["n"] and hist["n"] >= 3 and hist["avg_price"]:
        comps = comps * 0.7 + hist["avg_price"] * 0.3
        rationale.append(f"blended with {hist['n']} past {category} sales (avg {hist['avg_price']:.2f})")
    # charm pricing: snap to the nearest X.99
    price = math.floor(comps + 0.5) - 0.01
    price = round(min(max(price, pr["min_price"]), pr["max_price"]), 2)
    fees = st["marketplace_fees"]
    est_fees = fees["listing_fee"] + price * (fees["transaction_pct"] + fees["payment_pct"]) + fees["payment_fixed"]
    return {"price": price, "estimated_fees": round(est_fees, 2), "estimated_net": round(price - est_fees, 2),
            "rationale": "; ".join(rationale)}


def build_listing(sku, theme, profile, product_types, palettes, sizes) -> dict:
    rng = random.Random(sku)
    theme_t = _title_case(theme.strip())
    nouns = [TYPE_NOUNS[t] for t in product_types if t in TYPE_NOUNS]
    is_bundle = len(product_types) > 1
    if is_bundle:
        lead = f"{theme_t} Photo Booth Template Bundle"
        parts = [n for n in nouns if n not in ("Booth Buttons",)][:3]
        title = f"{lead} | {', '.join(parts)} | {len(palettes)} Colors | Instant Download"
    else:
        title = f"{theme_t} Photo Booth {nouns[0]} | {len(palettes)} Color Options | Instant Download"
    title = title[:140]

    # --- tags (max 13, each <= 20 chars)
    words = [w for w in re.findall(r"[a-z0-9']+", theme.lower()) if len(w) > 2]
    cand = []
    cand.append(f"{profile['category'].lower()} photo booth")
    if words:
        cand.append(f"{' '.join(words[-2:])} booth")
        cand.append(f"{words[-1]} photo booth")
        cand.append(f"{words[-1]} template")
    for t in product_types:
        cand += TYPE_TAGS.get(t, [])
    cand += BASE_TAGS
    cand += [f"{p.name.lower()} booth" for p in palettes]
    tags, seen = [], set()
    for t in cand:
        t = re.sub(r"\s+", " ", t).strip()[:20].strip()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
        if len(tags) == 13:
            break

    # --- description
    intro = rng.choice(INTROS).format(theme_l=theme.strip().lower())
    lines = [intro, "",
             "This is a DIGITAL DOWNLOAD for photo booth business owners. No physical item will be shipped.", "",
             "WHAT'S INCLUDED"]
    for t in product_types:
        sp = PRODUCT_SPECS[t]
        w, h = sizes.get(t, sp["size"])
        extra = ""
        if t == "strip_2x6":
            extra = f" + 4x6 double-strip print sheet ({w * 2}x{h}px)"
        if t == "buttons":
            extra = f" - {len(sp['labels'])} buttons: {', '.join(l if l == 'GIF' else l.title() for l in sp['labels'])}"
        if t == "welcome_video":
            extra = " - seamless looping MP4"
        fmt = "MP4" if t == "welcome_video" else "PNG"
        trans = " with transparent photo areas" if sp.get("transparent") and t != "buttons" else ""
        lines.append(f"- {sp['label']}: {w}x{h}px {fmt}{trans}{extra}")
    lines += [f"- {len(palettes)} color variations: {', '.join(p.name for p in palettes)}",
              "- Text-ready and blank versions of every print design (add your own names and date)",
              "",
              "HOW IT WORKS",
              "1. Purchase and download the ZIP file(s) instantly.",
              "2. Unzip and pick your color variation.",
              "3. Load the PNG/MP4 files into your photo booth software as overlay, template or start screen.",
              "4. Use the blank versions to add custom names and dates in any free image editor.",
              "",
              "LICENSE",
              "Commercial use is allowed for your own photo booth business and your clients' events. "
              "You may not resell, share or redistribute the template files themselves.",
              "",
              "PLEASE NOTE",
              "- Colors may vary slightly between screens and printers.",
              "- Print designs are 300 DPI; screen designs are optimised for 1080p displays.",
              "- All artwork is original and fonts are licensed for commercial use (SIL Open Font License)."]
    description = "\n".join(lines)
    return {"title": title, "description": description, "tags": tags}
