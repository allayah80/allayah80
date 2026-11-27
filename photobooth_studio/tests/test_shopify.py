"""Shopify mode: per-store ZIPs and fees, square images, SEO fields, import CSV, order import."""
import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from studio import config, db, listing, pipeline, sales, stores, themes, validate
from studio.palettes import parse_palette, variations


@pytest.fixture
def settings_with(monkeypatch):
    """Override settings for one test without touching config/settings.json."""
    def apply(**over):
        base = config.load_settings()
        base.update(over)
        monkeypatch.setattr(config, "load_settings", lambda: base)
        for mod in (stores, listing, pipeline):
            monkeypatch.setattr(mod, "load_settings", lambda: base, raising=False)
        return base
    return apply


def test_store_config_and_fees():
    st = config.load_settings()
    assert stores.enabled(st) == ["etsy", "shopify"]
    assert stores.cfg("etsy", st)["max_zip_mb"] == 20
    assert stores.cfg("shopify", st)["max_zip_mb"] > 20
    # Shopify: card fee only (2.9% + $0.30); Etsy: listing + transaction + payment fees
    assert stores.estimate_fees(20.0, "shopify", st) == round(20 * 0.029 + 0.30, 2)
    assert stores.estimate_fees(20.0, "etsy", st) > stores.estimate_fees(20.0, "shopify", st)


def test_legacy_settings_still_work():
    legacy = {"max_zip_mb": 15, "marketplace_fees": {"listing_fee": 0.2, "transaction_pct": 0.065,
                                                     "payment_pct": 0.03, "payment_fixed": 0.25}}
    assert stores.enabled(legacy) == ["etsy"]
    assert stores.cfg("etsy", legacy)["max_zip_mb"] == 15


def test_price_has_per_store_estimates():
    pr = listing.price_for(["strip_2x6", "overlay_4x6"], 3, "Wedding")
    assert set(pr["by_store"]) == {"etsy", "shopify"}
    assert pr["by_store"]["shopify"]["net"] > pr["by_store"]["etsy"]["net"]


def test_shopify_fields_and_html():
    prof = themes.resolve("Gatsby New Year's Eve")
    pals = variations(parse_palette("Black & Gold"), 4)
    lst = listing.build_listing("PB-T-0001", "Gatsby New Year's Eve", prof, config.PRODUCT_TYPES, pals, {})
    lst.update(listing.price_for(config.PRODUCT_TYPES, 4, prof["category"]))
    lst["shopify"] = stores.shopify_fields(lst, "PB-T-0001", "Gatsby New Year's Eve", prof["category"], 4)
    sh = lst["shopify"]
    assert len(sh["seo_title"]) <= 70 and len(sh["seo_description"]) <= 320
    only = stores.shopify_fields(lst, "X", "Gala", "Party", 2, product_types=["strip_2x6", "buttons"])
    assert "2x6 strips and buttons in 2 colors" in only["seo_description"]
    assert "welcome" not in only["seo_description"]
    assert sh["handle"] == "gatsby-new-year-s-eve-photo-booth-template-bundle-pb-t-0001"
    assert "<ul>" in sh["body_html"] and "<h3>" in sh["body_html"] and "<script" not in sh["body_html"]
    assert validate.check_listing(lst) == []
    row = stores.csv_row(lst, "PB-T-0001")
    assert row["Status"] == "draft" and row["Published"] == "FALSE" and row["Variant Requires Shipping"] == "FALSE"


def test_bundle_has_store_zips_square_images_and_csv(small_sizes):
    jid = db.add_job("Rose Gold Bridal Shower", "Blush & Gold", ["overlay_4x6", "gif_overlay"], 2, small_sizes, seed=8)
    pid = pipeline.build_job(jid, log=lambda *a: None)
    p = db.get_product(pid)
    assert p["valid"] == 1, p["validation"]["errors"]
    root = Path(p["bundle_dir"])
    assert (root / "dist" / "etsy").is_dir() and (root / "dist" / "shopify").is_dir()
    squares = sorted((root / "previews" / "square").glob("*.jpg"))
    assert len(squares) == 5 and all(Image.open(x).size == (2048, 2048) for x in squares)
    rows = list(csv.DictReader(open(root / "listing" / "shopify_product_import.csv", encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["Variant SKU"] == p["sku"] and rows[0]["Status"] == "draft"
    md = (root / "listing" / "listing.md").read_text()
    assert "## Etsy" in md and "## Shopify" in md
    # combined export of approved products
    db.set_product_status(pid, "approved")
    out = stores.export_products(db.rows("SELECT * FROM products WHERE status='approved'"))
    assert out and len(list(csv.DictReader(open(out, encoding="utf-8")))) == 1


def test_etsy_only_mode(settings_with, small_sizes):
    settings_with(stores=["etsy"])
    jid = db.add_job("Simple Birthday", "Pastel Party", ["buttons"], 1, small_sizes, seed=1)
    p = db.get_product(pipeline.build_job(jid, log=lambda *a: None))
    root = Path(p["bundle_dir"])
    assert all(z.startswith("dist/etsy/") for z in p["zip_files"])
    assert not (root / "listing" / "shopify_product_import.csv").exists()
    assert "shopify" not in json.loads((root / "listing" / "listing.json").read_text())


SHOPIFY_ORDERS = """Name,Email,Financial Status,Paid at,Fulfillment Status,Currency,Subtotal,Total,Lineitem quantity,Lineitem name,Lineitem price,Lineitem sku,Created at
#1001,a@x.com,paid,2026-11-20 14:03:11 -0500,fulfilled,USD,34.98,34.98,1,Gatsby Bundle,19.99,PB261127-0001,2026-11-20 14:02:00 -0500
#1001,,,,,,,,1,Neon Bundle,14.99,PB261127-0002,
#1002,b@x.com,refunded,2026-11-21 09:00:00 -0500,fulfilled,USD,19.99,19.99,1,Gatsby Bundle,19.99,PB261127-0001,2026-11-21 08:59:00 -0500
#1003,c@x.com,paid,2026-11-22 10:00:00 -0500,fulfilled,USD,39.98,39.98,2,Gatsby Bundle,19.99,PB261127-0001,2026-11-22 09:59:00 -0500
"""


def test_shopify_orders_import():
    added, skipped = sales.import_text(SHOPIFY_ORDERS)
    assert (added, skipped) == (3, 1)  # refunded order skipped
    rows = db.rows("SELECT * FROM sales ORDER BY id")
    assert [r["revenue"] for r in rows] == [19.99, 14.99, 39.98]  # unit price x qty, not order total
    assert rows[1]["date"] == "2026-11-20" and rows[1]["order_id"] == "#1001"  # order fields carried down
    assert all(r["source"] == "shopify" and r["fees"] > 0 for r in rows)
    assert sales.import_text(SHOPIFY_ORDERS) == (0, 4)  # re-import: all duplicates / refunded
