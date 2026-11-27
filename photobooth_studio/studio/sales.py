"""Import sales data from marketplace CSV exports (e.g. Etsy 'Sold Order Items').

This reads a file YOU download - it never logs in to any marketplace.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path

from . import db

ALIASES = {
    "date": ["sale date", "date", "order date", "date paid", "paid date", "created"],
    "order_id": ["order id", "order number", "order_id", "order", "transaction id"],
    "sku": ["sku", "listing sku", "item sku"],
    "title": ["item name", "title", "product", "listing title", "item title", "product name"],
    "quantity": ["quantity", "qty"],
    "revenue": ["item total", "order value", "revenue", "amount", "price", "sale price", "total"],
    "fees": ["fees", "fee", "transaction fees", "total fees"],
}

# Shopify "Export orders" CSV: one row per line item, unit prices, no fee column.
SHOPIFY_ALIASES = {
    "date": ["paid at", "created at"],
    "order_id": ["name"],
    "sku": ["lineitem sku"],
    "title": ["lineitem name"],
    "quantity": ["lineitem quantity"],
    "unit_price": ["lineitem price"],
    "status": ["financial status"],
}


def _money(v) -> float:
    v = re.sub(r"[^0-9.\-]", "", str(v or ""))
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _date(v) -> str:
    v = (v or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return v[:10] or datetime.now().date().isoformat()


def _map(headers):
    low = {h.strip().lower(): h for h in headers if h}
    m = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in low:
                m[key] = low[n]
                break
    return m


def is_shopify(headers) -> bool:
    low = {h.strip().lower() for h in headers if h}
    return {"lineitem name", "lineitem price"} <= low


def import_text(text: str, source="etsy") -> tuple[int, int]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if is_shopify(reader.fieldnames or []):
        return _import_shopify(reader)
    m = _map(reader.fieldnames or [])
    if "revenue" not in m or ("title" not in m and "sku" not in m):
        raise ValueError(f"CSV needs a price/total column and a title or SKU column. Found: {reader.fieldnames}")
    products = db.rows("SELECT sku, title FROM products")
    added = skipped = 0
    for i, row in enumerate(reader):
        g = lambda k: row.get(m[k], "") if k in m else ""
        title = g("title").strip()
        sku = g("sku").strip()
        if not sku and title:  # match by title prefix
            for p in products:
                if p["title"] and (title.lower()[:60] == p["title"].lower()[:60]):
                    sku = p["sku"]
                    break
        qty = int(_money(g("quantity")) or 1)
        revenue = _money(g("revenue"))
        if revenue <= 0:
            skipped += 1
            continue
        ok = db.add_sale(_date(g("date")), g("order_id") or f"row{i}-{title[:20]}", sku, title, qty, revenue,
                         _money(g("fees")), source)
        added += ok
        skipped += not ok
    return added, skipped


def _import_shopify(reader) -> tuple[int, int]:
    from . import stores
    low = {h.strip().lower(): h for h in reader.fieldnames if h}
    m = {k: low[n] for k, names in SHOPIFY_ALIASES.items() for n in reversed(names) if n in low}
    added = skipped = 0
    order_info = {}  # order-level columns are only filled on an order's first row
    for row in reader:
        g = lambda k: (row.get(m[k], "") or "").strip() if k in m else ""
        oid = g("order_id")
        info = order_info.setdefault(oid, {})
        for k in ("date", "status"):
            if g(k):
                info[k] = g(k)
        qty = int(_money(g("quantity")) or 1)
        revenue = round(_money(g("unit_price")) * qty, 2)
        if revenue <= 0 or info.get("status", "paid").lower() in ("refunded", "voided", "pending"):
            skipped += 1
            continue
        ok = db.add_sale(_date(info.get("date", "")), oid, g("sku"), g("title"), qty, revenue,
                         stores.estimate_fees(revenue, "shopify"), "shopify")
        added += ok
        skipped += not ok
    return added, skipped


def import_csv(path, source="etsy") -> tuple[int, int]:
    return import_text(Path(path).read_text(encoding="utf-8-sig"), source)


def summary(days: int | None = None) -> dict:
    where = ""
    params: tuple = ()
    if days:
        where = "WHERE date >= date('now', ?)"
        params = (f"-{days} days",)
    s = db.one(f"SELECT COALESCE(SUM(revenue),0) revenue, COALESCE(SUM(fees),0) fees, COALESCE(SUM(quantity),0) units, "
               f"COUNT(*) orders FROM sales {where}", params)
    c = db.one(f"SELECT COALESCE(SUM(amount),0) costs FROM costs {where}", params)
    s["costs"] = c["costs"]
    s["profit"] = round(s["revenue"] - s["fees"] - s["costs"], 2)
    return s


def top_sellers(limit=5):
    return db.rows("SELECT COALESCE(NULLIF(s.sku,''), s.title) AS item, MAX(s.title) title, SUM(s.quantity) units, "
                   "ROUND(SUM(s.revenue),2) revenue FROM sales s GROUP BY item ORDER BY revenue DESC LIMIT ?", (limit,))
