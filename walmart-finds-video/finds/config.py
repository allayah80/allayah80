"""Load and validate a video config (YAML).

The validator is deliberately strict about anything that could become a false
claim on screen: every price needs a verification date, "was" prices are only
shown when you mark them as shown on Walmart, and hook text can only use
numbers computed from your real product data.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .gfx import ROOT


class ConfigError(Exception):
    pass


@dataclass
class Product:
    id: str
    name: str            # full product name, shown small
    short_name: str      # headline name, shown big
    category: str
    image: Path
    price: float
    verified_on: dt.date
    was_price: float | None = None
    features: list = field(default_factory=list)
    voiceover: str = ""
    cue_words: list = field(default_factory=list)


@dataclass
class Variation:
    id: str
    look: str
    hook: str
    kicker: str
    background_image: Path | None = None


@dataclass
class Config:
    path: Path
    slug: str
    handle: str
    cta: str
    disclosure_pill: str
    disclosure_card: str
    disclosure_voiceover: str
    hook_voiceover: str
    products: list
    variations: list
    fps: int = 30
    target_seconds: float = 25.0
    min_seconds: float = 20.0
    max_seconds: float = 30.0
    voiceover_file: Path | None = None
    alignment: str = "auto"
    whisper_model: str = "base"
    loudnorm: bool = True
    captions: bool = True
    captions_on_hook: bool = False
    captions_on_cta: bool = False
    captions_on_disclosure: bool = False
    ai_label: str = "AI-generated background"
    price_note: str = "Walmart.com price as of {date} · prices can change"
    output_dir: Path = ROOT / "output"

    # ---- numbers that hook text may use (all computed, never typed) ----
    def facts(self):
        prices = [p.price for p in self.products]
        mx = max(prices)
        under = (math.floor(mx / 5) + 1) * 5  # strictly greater than every price
        return {
            "count": len(self.products),
            "count_word": _num_word(len(self.products)),
            "under_price": f"${under}",
            "max_price": f"${mx:,.2f}",
            "min_price": f"${min(prices):,.2f}",
        }

    def fill(self, text):
        try:
            return text.format(**self.facts())
        except KeyError as e:
            raise ConfigError(f"Unknown placeholder {e} in: {text!r}. "
                              f"Allowed: {', '.join('{'+k+'}' for k in self.facts())}")


def _num_word(n):
    words = "zero one two three four five six seven eight nine ten".split()
    return words[n] if n < len(words) else str(n)


def _req(d, key, where):
    if key not in d or d[key] in (None, ""):
        raise ConfigError(f"Missing '{key}' in {where}")
    return d[key]


def _date(v, where):
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise ConfigError(f"{where}: date must look like 2026-11-27, got {v!r}")


def _price(v, where):
    if isinstance(v, str):
        v = v.replace("$", "").replace(",", "").strip()
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: price must be a number like 29.00, got {v!r}")
    if v <= 0:
        raise ConfigError(f"{where}: price must be positive")
    return round(v, 2)


def load(path) -> Config:
    path = Path(path).resolve()
    base = path.parent.parent if path.parent.name == "config" else path.parent
    raw = yaml.safe_load(path.read_text())

    def rel(p):
        if not p:
            return None
        q = Path(p)
        return q if q.is_absolute() else (base / q).resolve()

    brand = raw.get("brand", {})
    disc = _req(raw, "disclosure", "config")
    vid = raw.get("video", {})
    vo = raw.get("voiceover", {}) or {}
    cap = raw.get("captions", {}) or {}

    default_date = raw.get("prices_verified_on")
    products = []
    for i, p in enumerate(_req(raw, "products", "config")):
        where = f"product #{i + 1} ({p.get('id', '?')})"
        img = rel(_req(p, "image", where))
        if not img.exists():
            raise ConfigError(f"{where}: image not found: {img}")
        vdate = p.get("price_verified_on", default_date)
        if not vdate:
            raise ConfigError(f"{where}: add price_verified_on (the date you checked the price on Walmart)")
        was = p.get("was_price")
        if was is not None and not p.get("was_price_shown_on_walmart", False):
            print(f"  note: {where}: was_price ignored (set was_price_shown_on_walmart: true "
                  "only if Walmart itself displays that 'was' price)")
            was = None
        price = _price(_req(p, "price", where), where)
        if was is not None:
            was = _price(was, where)
            if was <= price:
                raise ConfigError(f"{where}: was_price must be higher than price")
        products.append(Product(
            id=str(_req(p, "id", where)),
            name=str(_req(p, "name", where)),
            short_name=str(p.get("short_name") or p["name"]),
            category=str(p.get("category", "")),
            image=img,
            price=price,
            verified_on=_date(vdate, where),
            was_price=was,
            features=[str(f) for f in p.get("features", [])][:4],
            voiceover=str(p.get("voiceover", "")).strip(),
            cue_words=[str(w).lower() for w in p.get("cue_words", [])],
        ))
    if not 1 <= len(products) <= 5:
        raise ConfigError("Use between 1 and 5 products per video (3 fits 20-30 s best)")

    variations = []
    for v in _req(raw, "variations", "config"):
        variations.append(Variation(
            id=str(_req(v, "id", "variation")),
            look=str(_req(v, "look", "variation")),
            hook=str(_req(v, "hook", "variation")),
            kicker=str(v.get("kicker", "")),
            background_image=rel(v.get("ai_background")),
        ))
        bg = variations[-1].background_image
        if bg and not bg.exists():
            raise ConfigError(f"variation {v['id']}: ai_background not found: {bg}")

    cfg = Config(
        path=path,
        slug=str(raw.get("slug") or path.stem),
        handle=str(brand.get("handle", "@thelayahedit")),
        cta=str(brand.get("cta", "Shop my Walmart finds — link in bio.")),
        disclosure_pill=str(_req(disc, "on_screen_short", "disclosure")),
        disclosure_card=str(_req(disc, "on_screen_full", "disclosure")),
        disclosure_voiceover=str(disc.get("audible_script", "")).strip(),
        hook_voiceover=str(raw.get("hook_voiceover", "")).strip(),
        products=products,
        variations=variations,
        fps=int(vid.get("fps", 30)),
        target_seconds=float(vid.get("target_seconds", 25)),
        voiceover_file=rel(vo.get("file")),
        alignment=str(vo.get("alignment", "auto")),
        whisper_model=str(vo.get("whisper_model", "base")),
        loudnorm=bool(vo.get("normalize_loudness", True)),
        captions=bool(cap.get("enabled", True)),
        captions_on_hook=bool(cap.get("show_during_hook", False)),
        captions_on_cta=bool(cap.get("show_during_cta", False)),
        captions_on_disclosure=bool(cap.get("show_during_disclosure", False)),
        ai_label=str(raw.get("ai_background_label", "AI-generated background")),
        price_note=str(raw.get("price_note", Config.price_note)),
        output_dir=rel(vid.get("output_dir", "output")),
    )
    if cfg.voiceover_file and not cfg.voiceover_file.exists():
        raise ConfigError(f"voiceover file not found: {cfg.voiceover_file}")
    for v in cfg.variations:
        cfg.fill(v.hook)
        cfg.fill(v.kicker)
    _check_script_prices(cfg)
    return cfg


_money = re.compile(r"\$\s?(\d[\d,]*(?:\.\d\d)?)")


def _check_script_prices(cfg: Config):
    """Warn if a voiceover line mentions a dollar amount that isn't the product's price."""
    for p in cfg.products:
        for m in _money.findall(p.voiceover):
            if abs(float(m.replace(",", "")) - p.price) > 0.001 and not (
                p.was_price and abs(float(m.replace(",", "")) - p.was_price) < 0.001
            ):
                print(f"  WARNING: voiceover for '{p.id}' says ${m} but the verified price is ${p.price:.2f}")
