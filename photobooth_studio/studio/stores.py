"""Store profiles (Etsy, Shopify): file limits, fees, SEO text and Shopify import CSV.

Nothing here connects to a store. The Shopify CSV is a file YOU import in
Shopify admin (Products -> Import); every product in it is created as a
draft, unpublished, with no shipping.
"""
from __future__ import annotations

import csv
import html
import json
import re
from datetime import date
from pathlib import Path

from .config import load_settings, out_dirs

STORES = ("etsy", "shopify")

DEFAULTS = {
    "etsy": {"max_zip_mb": 20,
             "fees": {"listing_fee": 0.20, "transaction_pct": 0.065, "payment_pct": 0.03, "payment_fixed": 0.25}},
    "shopify": {"max_zip_mb": 500,
                "fees": {"listing_fee": 0.0, "transaction_pct": 0.0, "payment_pct": 0.029, "payment_fixed": 0.30},
                "product_type": "Digital Download"},
}


def enabled(settings: dict | None = None) -> list[str]:
    st = settings or load_settings()
    stores = [s for s in st.get("stores", ["etsy"]) if s in STORES]
    return stores or ["etsy"]


def cfg(store: str, settings: dict | None = None) -> dict:
    st = settings or load_settings()
    c = json.loads(json.dumps(DEFAULTS[store]))
    # legacy single-store keys (older settings files)
    if store == "etsy":
        if "max_zip_mb" in st:
            c["max_zip_mb"] = st["max_zip_mb"]
        if "marketplace_fees" in st:
            c["fees"] = st["marketplace_fees"]
    for k, v in st.get("store_settings", {}).get(store, {}).items():
        c[k] = {**c[k], **v} if isinstance(v, dict) and isinstance(c.get(k), dict) else v
    return c


def estimate_fees(price: float, store: str, settings: dict | None = None) -> float:
    f = cfg(store, settings)["fees"]
    return round(f["listing_fee"] + price * (f["transaction_pct"] + f["payment_pct"]) + f["payment_fixed"], 2)


# ---------------------------------------------------------------- Shopify copy
def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rsplit(" ", 1)[0].rstrip(" ,|-") + "…"


def handle(title: str, sku: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower().split("|")[0]).strip("-")[:60].strip("-")
    return f"{base}-{sku.lower()}"


def body_html(description: str) -> str:
    """Turn the plain-text description into simple HTML for Shopify."""
    out, in_list = [], None
    for line in description.split("\n"):
        line = line.rstrip()
        bullet = re.match(r"^- (.*)", line)
        number = re.match(r"^\d+\. (.*)", line)
        tag = "ul" if bullet else "ol" if number else None
        if in_list and tag != in_list:
            out.append(f"</{in_list}>")
            in_list = None
        if tag:
            if not in_list:
                out.append(f"<{tag}>")
                in_list = tag
            out.append(f"<li>{html.escape((bullet or number).group(1))}</li>")
        elif line.isupper() and len(line) < 40:
            out.append(f"<h3>{html.escape(line.title())}</h3>")
        elif line:
            out.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        out.append(f"</{in_list}>")
    return "\n".join(out)


SEO_NOUNS = {"welcome_screen": "welcome screen", "welcome_video": "animated start screen",
             "strip_2x6": "2x6 strips", "overlay_4x6": "4x6 overlays", "gif_overlay": "GIF overlays",
             "buttons": "buttons"}


def shopify_fields(listing: dict, sku: str, theme: str, category: str, n_colors: int, settings=None,
                   product_types=None) -> dict:
    st = settings or load_settings()
    short = listing["title"].split("|")[0].strip()
    seo_title = _clip(f"{short} | {n_colors} Colors", 70)
    items = [SEO_NOUNS[t] for t in (product_types or SEO_NOUNS) if t in SEO_NOUNS]
    items_txt = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    seo_desc = _clip(f"Instant download {theme.strip().lower()} photo booth templates for photo booth businesses: "
                     f"{items_txt} in {n_colors} colors. Commercial use license.", 320)
    tags = [category, "Photo Booth Template", "Digital Download", f"{n_colors} Colors"] + \
           [t.title() for t in listing.get("tags", [])[:8]]
    seen, uniq = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return {"handle": handle(listing["title"], sku), "seo_title": seo_title, "seo_description": seo_desc,
            "body_html": body_html(listing["description"]), "vendor": st.get("shop_name", ""),
            "product_type": cfg("shopify", st).get("product_type", "Digital Download"), "tags": uniq}


# ---------------------------------------------------------------- Shopify CSV
CSV_COLUMNS = ["Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published", "Option1 Name",
               "Option1 Value", "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
               "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
               "Variant Requires Shipping", "Variant Taxable", "Gift Card", "SEO Title", "SEO Description", "Status"]


def csv_row(listing: dict, sku: str) -> dict:
    s = listing["shopify"]
    return {"Handle": s["handle"], "Title": listing["title"].split("|")[0].strip(), "Body (HTML)": s["body_html"],
            "Vendor": s["vendor"], "Type": s["product_type"], "Tags": ", ".join(s["tags"]),
            "Published": "FALSE", "Option1 Name": "Title", "Option1 Value": "Default Title", "Variant SKU": sku,
            "Variant Grams": "0", "Variant Inventory Tracker": "", "Variant Inventory Policy": "continue",
            "Variant Fulfillment Service": "manual", "Variant Price": f"{listing['price']:.2f}",
            "Variant Requires Shipping": "FALSE", "Variant Taxable": "TRUE", "Gift Card": "FALSE",
            "SEO Title": s["seo_title"], "SEO Description": s["seo_description"], "Status": "draft"}


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def export_products(products: list[dict]) -> Path | None:
    """One Shopify import CSV for several products (e.g. everything approved)."""
    rows = []
    for p in products:
        lj = Path(p["bundle_dir"]) / "listing" / "listing.json"
        if lj.exists():
            listing = json.loads(lj.read_text())
            if "shopify" in listing:
                rows.append(csv_row(listing, p["sku"]))
    if not rows:
        return None
    exports = out_dirs()["base"] / "exports"
    return write_csv(rows, exports / f"shopify_import_{date.today():%Y-%m-%d}.csv")
