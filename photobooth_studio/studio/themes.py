"""Theme profiles (style rules) and the copyright / trademark safety check.

A theme is free text such as "Rustic Boho Wedding". It is matched to a style
profile by keyword. Profiles only use procedural, original artwork (shapes we
draw ourselves) and OFL-licensed fonts, so every output is commercially safe.
"""
from __future__ import annotations

import re

from .config import load_settings

# Fonts: (file, variation name or None). All are SIL Open Font License.
FONT_SCRIPT = ("GreatVibes-Regular.ttf", None)
FONT_SERIF = ("PlayfairDisplay-VF.ttf", "Bold")
FONT_DECO = ("Cinzel-VF.ttf", "Bold")
FONT_SANS = ("Montserrat-VF.ttf", "SemiBold")
FONT_SANS_BOLD = ("Montserrat-VF.ttf", "ExtraBold")
FONT_FUN = ("Pacifico-Regular.ttf", None)

PROFILES: dict[str, dict] = {
    "wedding": {
        "keywords": ["wedding", "bridal", "bride", "engagement", "anniversary", "vow", "elopement", "rehearsal"],
        "motifs": ["botanical", "sparkle"],
        "frame": "double",
        "title_font": FONT_SCRIPT, "body_font": FONT_SERIF,
        "headlines": ["Happily Ever After", "Love & Laughter", "Cheers to Love"],
        "placeholder": "Names Here  •  00.00.2027",
        "category": "Wedding",
    },
    "birthday": {
        "keywords": ["birthday", "bday", "sweet 16", "quinceanera", "30th", "40th", "50th", "21st"],
        "motifs": ["balloons", "confetti"],
        "frame": "none",
        "title_font": FONT_FUN, "body_font": FONT_SANS_BOLD,
        "headlines": ["Happy Birthday", "Let's Party", "Make a Wish"],
        "placeholder": "Name's Birthday  •  00.00.2027",
        "category": "Birthday",
    },
    "christmas": {
        "keywords": ["christmas", "holiday", "xmas", "winter", "snow", "festive", "noel"],
        "motifs": ["snowflakes", "stars", "bokeh"],
        "frame": "double",
        "title_font": FONT_SCRIPT, "body_font": FONT_DECO,
        "headlines": ["Merry & Bright", "Happy Holidays", "Season's Greetings"],
        "placeholder": "Company Holiday Party  •  2027",
        "category": "Holiday",
    },
    "newyear": {
        "keywords": ["new year", "nye", "new years", "countdown", "gatsby", "roaring", "1920s", "art deco"],
        "motifs": ["deco", "sparkle", "confetti"],
        "frame": "deco",
        "title_font": FONT_DECO, "body_font": FONT_SANS,
        "headlines": ["Cheers to the New Year", "Happy New Year", "Pop the Bubbly"],
        "placeholder": "New Year's Eve  •  2027",
        "category": "New Year",
    },
    "halloween": {
        "keywords": ["halloween", "spooky", "fall fest", "trick or treat", "costume"],
        "motifs": ["pumpkins", "bats", "stars"],
        "frame": "none",
        "title_font": FONT_FUN, "body_font": FONT_SANS_BOLD,
        "headlines": ["Spooky Season", "Trick or Treat", "Boo!"],
        "placeholder": "Halloween Bash  •  10.31.2027",
        "category": "Halloween",
    },
    "baby": {
        "keywords": ["baby", "shower", "gender reveal", "christening", "baptism", "sprinkle", "first birthday"],
        "motifs": ["clouds", "hearts", "stars"],
        "frame": "none",
        "title_font": FONT_SCRIPT, "body_font": FONT_SANS,
        "headlines": ["Oh Baby", "Welcome Little One", "Baby Shower"],
        "placeholder": "Baby Name  •  00.00.2027",
        "category": "Baby Shower",
    },
    "graduation": {
        "keywords": ["graduation", "grad", "class of", "prom", "homecoming", "school", "senior"],
        "motifs": ["stars", "confetti"],
        "frame": "double",
        "title_font": FONT_SERIF, "body_font": FONT_SANS_BOLD,
        "headlines": ["Congrats Grad", "The Future Is Bright", "Class of 2027"],
        "placeholder": "Graduate Name  •  2027",
        "category": "Graduation",
    },
    "valentine": {
        "keywords": ["valentine", "galentine", "love", "romance", "date night"],
        "motifs": ["hearts", "sparkle"],
        "frame": "none",
        "title_font": FONT_SCRIPT, "body_font": FONT_SERIF,
        "headlines": ["All You Need Is Love", "Be Mine", "XOXO"],
        "placeholder": "Event Name  •  02.14.2027",
        "category": "Valentine's Day",
    },
    "summer": {
        "keywords": ["summer", "beach", "tropical", "luau", "pool", "ocean", "coastal", "spring"],
        "motifs": ["waves", "botanical", "sparkle"],
        "frame": "none",
        "title_font": FONT_FUN, "body_font": FONT_SANS_BOLD,
        "headlines": ["Good Vibes Only", "Hello Summer", "Sun's Out"],
        "placeholder": "Event Name  •  00.00.2027",
        "category": "Summer",
    },
    "corporate": {
        "keywords": ["corporate", "conference", "gala", "launch", "business", "awards", "fundraiser", "expo", "brand"],
        "motifs": ["geometric", "bokeh"],
        "frame": "double",
        "title_font": FONT_DECO, "body_font": FONT_SANS,
        "headlines": ["Welcome", "Celebrate Success", "Strike a Pose"],
        "placeholder": "Your Event Name  •  2027",
        "category": "Corporate Event",
    },
    "default": {
        "keywords": [],
        "motifs": ["bokeh", "confetti", "sparkle"],
        "frame": "none",
        "title_font": FONT_SERIF, "body_font": FONT_SANS,
        "headlines": ["Strike a Pose", "Say Cheese", "Let's Celebrate"],
        "placeholder": "Your Event Name  •  00.00.2027",
        "category": "Party",
    },
}

# Optional style words that adjust a profile.
STYLE_WORDS = {
    "rustic": {"motifs_add": ["botanical"]},
    "boho": {"motifs_add": ["botanical"], "frame": "none"},
    "floral": {"motifs_add": ["botanical"]},
    "elegant": {"frame": "double"},
    "glam": {"motifs_add": ["sparkle"]},
    "minimal": {"motifs": ["geometric"], "frame": "double"},
    "modern": {"motifs_add": ["geometric"]},
    "deco": {"frame": "deco", "motifs_add": ["deco"]},
    "starry": {"motifs_add": ["stars"]},
    "disco": {"motifs_add": ["bokeh", "sparkle"]},
}

# Characters, brands and franchises we must never imitate. Matched as whole
# words, case-insensitively, against themes, titles, descriptions and tags.
BLOCKED_TERMS = [
    "disney", "pixar", "marvel", "avengers", "spiderman", "spider-man", "batman", "superman",
    "dc comics", "star wars", "mickey", "minnie", "frozen", "elsa", "moana", "encanto",
    "barbie", "hello kitty", "sanrio", "pokemon", "pikachu", "nintendo", "mario", "zelda",
    "minecraft", "fortnite", "roblox", "harry potter", "hogwarts", "bluey", "peppa",
    "paw patrol", "cocomelon", "sesame street", "looney tunes", "sonic", "lego", "nfl",
    "nba", "mlb", "nhl", "fifa", "olympic", "coca-cola", "coke", "pepsi", "starbucks",
    "nike", "adidas", "gucci", "chanel", "louis vuitton", "tiffany", "taylor swift",
    "swiftie", "eras tour", "beyonce", "barney", "care bears", "my little pony",
    "transformers", "jurassic", "toy story", "lion king", "stranger things", "squid game",
    "wednesday addams", "grinch", "dr. seuss", "dr seuss", "snoopy", "peanuts", "garfield",
    "shrek", "minions", "despicable me", "sesame", "teletubbies", "smurfs", "bratz",
]


def blocked_terms() -> list[str]:
    try:
        extra = load_settings().get("blocked_terms_extra", [])
    except Exception:
        extra = []
    return BLOCKED_TERMS + [t.lower() for t in extra]


def find_blocked(text: str) -> list[str]:
    t = (text or "").lower()
    hits = []
    for term in blocked_terms():
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", t):
            hits.append(term)
    return hits


def resolve(theme: str) -> dict:
    """Return a style profile (copy) for a free-text theme."""
    t = theme.lower()
    chosen = "default"
    for key, prof in PROFILES.items():
        if any(k in t for k in prof["keywords"]):
            chosen = key
            break
    prof = {k: (list(v) if isinstance(v, list) else v) for k, v in PROFILES[chosen].items()}
    prof["key"] = chosen
    for word, mod in STYLE_WORDS.items():
        if word in t:
            if "motifs" in mod:
                prof["motifs"] = list(mod["motifs"])
            for m in mod.get("motifs_add", []):
                if m not in prof["motifs"]:
                    prof["motifs"].append(m)
            if "frame" in mod:
                prof["frame"] = mod["frame"]
    prof["motifs"] = prof["motifs"][:3]
    return prof
