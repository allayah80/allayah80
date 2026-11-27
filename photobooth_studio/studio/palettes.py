"""Color palette parsing, roles, contrast and deterministic variations."""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass

HEX_RE = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

# Curated presets (name -> [background, primary, accent, text]).
PRESETS: dict[str, list[str]] = {
    "Blush & Gold": ["#FBEFEF", "#E8A5B4", "#C9A227", "#5A3A44"],
    "Navy & Gold": ["#0F1E3D", "#24407A", "#D4AF37", "#F7F3E8"],
    "Sage Garden": ["#F3F5EE", "#8FA98B", "#C8A96A", "#334433"],
    "Black & Gold": ["#111111", "#2B2B2B", "#D4AF37", "#F5F0E1"],
    "Lavender Dream": ["#F4F0FA", "#B39DDB", "#E6B8D8", "#4A3B66"],
    "Emerald Luxe": ["#0E3B2E", "#1F6F54", "#E3C77A", "#F4EFE2"],
    "Burgundy Rose": ["#FFF5F3", "#7A1F35", "#D9A5A0", "#3D1020"],
    "Pastel Party": ["#FFF8F0", "#FFB5C2", "#9ED8DB", "#4B4453"],
    "Silver Frost": ["#EEF3F8", "#9FB3C8", "#C0C7D0", "#24344D"],
    "Terracotta Boho": ["#FAF1E6", "#C8683F", "#E2B07A", "#4A2A1A"],
    "Neon Night": ["#140A2E", "#FF3FA4", "#22E3FF", "#FFFFFF"],
    "Ocean Breeze": ["#F0FAFB", "#3AA6B9", "#FFD0A6", "#11404A"],
}

# Small named-color table used to label variations ("Rose", "Navy" ...).
COLOR_NAMES = {
    "Red": "#C62828", "Rose": "#E8A5B4", "Pink": "#F48FB1", "Coral": "#FF7F6E",
    "Orange": "#F28C28", "Peach": "#FFCBA4", "Gold": "#D4AF37", "Yellow": "#F5D547",
    "Olive": "#8A8D3F", "Sage": "#8FA98B", "Green": "#3E8E41", "Emerald": "#1F6F54",
    "Teal": "#2A9D8F", "Mint": "#7FD8A8", "Aqua": "#5CC8D7", "Sky": "#87BFE8", "Blue": "#2F6DB5",
    "Navy": "#1B2A4E", "Lavender": "#B39DDB", "Purple": "#7B4BA8", "Plum": "#6A2C5A",
    "Burgundy": "#7A1F35", "Terracotta": "#C8683F", "Brown": "#6D4C41",
    "Black": "#151515", "Charcoal": "#3A3A3A", "Silver": "#B8BEC6", "Ivory": "#FBF7EC",
    "White": "#FFFFFF",
}


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(c) -> str:
    return "#{:02X}{:02X}{:02X}".format(*[max(0, min(255, int(round(v)))) for v in c[:3]])


def luminance(c) -> float:
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def nearest_name(c) -> str:
    best, bd = "Color", 1e9
    for name, hx in COLOR_NAMES.items():
        r = hex_to_rgb(hx)
        d = sum((c[i] - r[i]) ** 2 for i in range(3))
        if d < bd:
            best, bd = name, d
    return best


@dataclass
class Palette:
    name: str
    bg: tuple
    primary: tuple
    accent: tuple
    text: tuple

    @property
    def colors(self):
        return [self.bg, self.primary, self.accent, self.text]

    def hexes(self) -> list[str]:
        return [rgb_to_hex(c) for c in self.colors]

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")

    def text_on(self, bg) -> tuple:
        """Best readable text color for a given background."""
        for cand in (self.text, self.primary, self.accent):
            if contrast(cand, bg) >= 4.5:
                return cand
        return (20, 20, 20) if luminance(bg) > 0.4 else (250, 250, 250)

    def to_dict(self):
        return {"name": self.name, "colors": self.hexes()}


def parse_palette(value: str | list[str], name: str | None = None) -> Palette:
    """Accepts a preset name, or 2-4 hex colors: background, primary, accent, text."""
    if isinstance(value, str) and value.strip() in PRESETS:
        name = name or value.strip()
        value = PRESETS[value.strip()]
    if isinstance(value, str):
        hexes = ["#" + m for m in HEX_RE.findall(value)]
    else:
        hexes = list(value)
    if len(hexes) < 2:
        raise ValueError("Palette needs a preset name or at least 2 hex colors "
                         "(background, primary[, accent, text]).")
    cols = [hex_to_rgb(h) for h in hexes[:4]]
    bg, primary = cols[0], cols[1]
    accent = cols[2] if len(cols) > 2 else mix(primary, (212, 175, 55), 0.5)
    text = cols[3] if len(cols) > 3 else ((30, 30, 30) if luminance(bg) > 0.4 else (248, 248, 248))
    if not name:
        name = f"{nearest_name(primary)} {nearest_name(accent)}"
        if name.split()[0] == name.split()[1]:
            name = name.split()[0]
    return Palette(name, bg, primary, accent, text)


def _sat(c):
    return colorsys.rgb_to_hls(*[v / 255 for v in c])[2] * (1 - abs(2 * colorsys.rgb_to_hls(*[v / 255 for v in c])[1] - 1))


def variation_name(p: "Palette", taken: list[str]) -> str:
    """Name a palette after its most vivid color, e.g. 'Lavender' or 'Aqua Noir'."""
    hero, other = sorted([p.primary, p.accent], key=_sat, reverse=True)
    name = nearest_name(hero) + (" Noir" if luminance(p.bg) < 0.2 else "")
    if name in taken:
        name = f"{nearest_name(hero)} & {nearest_name(other)}"
    n = 2
    base = name
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return name


def _rotate(c, deg: float, keep_neutral=True):
    h, l, s = colorsys.rgb_to_hls(*[v / 255 for v in c])
    if keep_neutral and s < 0.08:
        return c
    h = (h + deg / 360) % 1.0
    return tuple(int(round(v * 255)) for v in colorsys.hls_to_rgb(h, l, s))


def variations(base: Palette, count: int) -> list[Palette]:
    """Deterministic color variations: the original, hue rotations, then presets.

    Neutral colors (whites, blacks, greys) are preserved during hue rotation so
    the design keeps its character.
    """
    out = [base]
    seen = {tuple(base.hexes())}
    for deg in (150, 210, 90, 270, 45, 315, 120, 240):
        if len(out) >= count:
            break
        cols = [_rotate(c, deg) for c in base.colors]
        p = Palette("", *cols)
        if tuple(p.hexes()) in seen:
            continue
        p.name = variation_name(p, [o.name for o in out])
        seen.add(tuple(p.hexes()))
        out.append(p)
    for pname, pcols in PRESETS.items():
        if len(out) >= count:
            break
        p = parse_palette(pcols, name=pname)
        if tuple(p.hexes()) not in seen:
            seen.add(tuple(p.hexes()))
            out.append(p)
    return out[:count]
