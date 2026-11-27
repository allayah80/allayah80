"""Paths, product specifications and user settings."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
SETTINGS_FILE = ROOT / "config" / "settings.json"

# Everything generated lives under OUTPUT (override with PBS_OUTPUT for tests).
OUTPUT = Path(os.environ.get("PBS_OUTPUT", ROOT / "output"))


def out_dirs() -> dict[str, Path]:
    base = Path(os.environ.get("PBS_OUTPUT", OUTPUT))
    d = {
        "base": base,
        "bundles": base / "bundles",
        "reports": base / "reports",
        "logs": base / "logs",
        "db": base / "studio.sqlite3",
    }
    for k, p in d.items():
        if k != "db":
            p.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Product specs. Sizes are pixels; print products are 300 DPI.
# ---------------------------------------------------------------------------
PRODUCT_SPECS: dict[str, dict] = {
    "welcome_screen": {
        "label": "Welcome Screen",
        "folder": "01_Welcome_Screens",
        "size": (1920, 1080),
        "dpi": 72,
        "transparent": False,
    },
    "welcome_video": {
        "label": "Animated Welcome Screen",
        "folder": "02_Animated_Welcome_Screens",
        "size": (1920, 1080),
        "dpi": 72,
        "transparent": False,
    },
    "strip_2x6": {
        "label": "2x6 Photo Strip",
        "folder": "03_Photo_Strips_2x6",
        "size": (600, 1800),
        "dpi": 300,
        "transparent": True,
        "photos": 3,
    },
    "overlay_4x6": {
        "label": "4x6 Print Overlay",
        "folder": "04_Print_Overlays_4x6",
        "size": (1800, 1200),
        "dpi": 300,
        "transparent": True,
        "photos": 1,
    },
    "gif_overlay": {
        "label": "GIF / Boomerang Overlay",
        "folder": "05_GIF_Overlays",
        "size": (1080, 1080),
        "dpi": 72,
        "transparent": True,
    },
    "buttons": {
        "label": "Experience Buttons",
        "folder": "06_Experience_Buttons",
        "size": (800, 260),
        "dpi": 72,
        "transparent": True,
        "labels": ["START", "PHOTO", "GIF", "BOOMERANG", "VIDEO",
                   "RETAKE", "PRINT", "SHARE", "DONE"],
    },
}

PRODUCT_TYPES = list(PRODUCT_SPECS)


def spec(ptype: str, size: tuple[int, int] | None = None) -> dict:
    s = deepcopy(PRODUCT_SPECS[ptype])
    if size:
        s["size"] = (int(size[0]), int(size[1]))
    return s


def load_settings() -> dict:
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)
