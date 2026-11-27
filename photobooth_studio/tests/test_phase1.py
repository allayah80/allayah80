"""Phase 1: rendering, palettes, safety, validation, listing, packaging, database."""
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from studio import db, listing, packager, pipeline, render, themes, validate
from studio.palettes import contrast, parse_palette, variations


def design(theme="Elegant Wedding"):
    prof = themes.resolve(theme)
    return render.Design(theme, prof, 123, prof["headlines"][0], prof["placeholder"])


# ------------------------------------------------------------ palettes
def test_parse_hex_and_preset():
    p = parse_palette("#FBEFEF, #E8A5B4, #C9A227")
    assert p.hexes()[:3] == ["#FBEFEF", "#E8A5B4", "#C9A227"]
    assert parse_palette("Navy & Gold").name == "Navy & Gold"
    with pytest.raises(ValueError):
        parse_palette("not a palette")


def test_variations_unique_and_deterministic():
    base = parse_palette("Blush & Gold")
    v1, v2 = variations(base, 6), variations(base, 6)
    assert len(v1) == 6
    assert [p.hexes() for p in v1] == [p.hexes() for p in v2]
    assert len({tuple(p.hexes()) for p in v1}) == 6
    assert len({p.name for p in v1}) == 6
    assert v1[0].hexes() == base.hexes()


def test_text_on_is_readable():
    p = parse_palette("Black & Gold")
    for bg in [(0, 0, 0), (255, 255, 255), p.primary]:
        assert contrast(p.text_on(bg), bg) >= 4.5


# ------------------------------------------------------------ safety
@pytest.mark.parametrize("theme", ["Frozen Elsa Birthday", "Taylor Swift Eras Tour Party", "mickey mouse"])
def test_blocked_themes(theme):
    assert themes.find_blocked(theme)


@pytest.mark.parametrize("theme", ["Rustic Boho Wedding", "Snowy Winter Wonderland", "Cocktail Hour"])
def test_allowed_themes(theme):
    assert not themes.find_blocked(theme)


def test_theme_profiles():
    assert themes.resolve("Gatsby New Year")["key"] == "newyear"
    assert themes.resolve("Halloween party")["key"] == "halloween"
    assert themes.resolve("Something unusual")["key"] == "default"


# ------------------------------------------------------------ renderers
@pytest.mark.parametrize("ptype,size", [("strip_2x6", (200, 600)), ("overlay_4x6", (600, 400)),
                                        ("overlay_4x6", (400, 600)), ("gif_overlay", (360, 360))])
def test_overlays_have_transparent_windows(ptype, size, tmp_path):
    pal = parse_palette("Sage Garden")
    img = render.RENDERERS[ptype](design(), pal, with_text=True, size=size)
    assert img.size == size and img.mode == "RGBA"
    path = render.save_png(img, tmp_path / "x.png")
    res = validate.check_image(path, size, transparent=True, dpi=300 if ptype != "gif_overlay" else 72,
                               windows=img.info["windows"])
    assert res["ok"], res["issues"]


def test_welcome_screen_opaque_and_portrait(tmp_path):
    pal = parse_palette("Navy & Gold")
    for size in [(480, 270), (270, 480)]:
        img = render.welcome_screen(design(), pal, size=size)
        p = render.save_png(img, tmp_path / f"w{size[0]}.png")
        assert validate.check_image(p, size, transparent=False)["ok"]


def test_same_seed_same_layout_different_colors():
    d = design()
    a = np.asarray(render.overlay_4x6(d, parse_palette("Sage Garden"), size=(300, 200)))
    b = np.asarray(render.overlay_4x6(d, parse_palette("Sage Garden"), size=(300, 200)))
    c = np.asarray(render.overlay_4x6(d, parse_palette("Navy & Gold"), size=(300, 200)))
    assert (a == b).all()
    assert (a[..., 3] == c[..., 3]).mean() > 0.97  # identical photo windows/shape
    assert not (a == c).all()


def test_button(tmp_path):
    img = render.button(design(), parse_palette("Pastel Party"), "BOOMERANG", (400, 130))
    p = render.save_png(img, tmp_path / "b.png")
    assert validate.check_image(p, (400, 130), transparent=True)["ok"]


def test_strip_double_sheet():
    strip = render.strip_2x6(design(), parse_palette("Sage Garden"), size=(200, 600))
    sheet = render.strip_double(strip)
    assert sheet.size == (400, 600) and len(sheet.info["windows"]) == 6


# ------------------------------------------------------------ validation
def test_validator_catches_bad_files(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (100, 100), "white").save(blank)
    r = validate.check_image(blank, (200, 200), transparent=True)
    assert not r["ok"] and len(r["issues"]) >= 2
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert not validate.check_image(bad)["ok"]
    assert not validate.check_image(tmp_path / "missing.png")["ok"]


def test_listing_rules():
    issues = validate.check_listing({"title": "Disney Party Overlay", "description": "", "tags": ["x" * 25], "price": 0})
    assert len(issues) == 3


# ------------------------------------------------------------ listing/pricing
def test_listing_constraints():
    prof = themes.resolve("Rustic Boho Wedding")
    pals = variations(parse_palette("Sage Garden"), 4)
    types = ["welcome_screen", "strip_2x6", "overlay_4x6", "gif_overlay", "buttons", "welcome_video"]
    lst = listing.build_listing("PB-TEST", "Rustic Boho Wedding", prof, types, pals, {})
    lst.update(listing.price_for(types, 4, prof["category"]))
    assert validate.check_listing(lst) == []
    assert len(lst["tags"]) == 13
    assert 4.99 <= lst["price"] <= 39.99 and str(lst["price"]).endswith(".99")
    assert lst["estimated_net"] < lst["price"]


# ------------------------------------------------------------ packaging
def test_package_split(tmp_path):
    prod = tmp_path / "prod"
    for var in ("rose", "navy", "sage"):
        f = prod / "01_Welcome_Screens" / var / "a.bin"
        f.parent.mkdir(parents=True)
        f.write_bytes(np.random.default_rng(1).bytes(400_000))
    packager.write_docs(prod, "SKU", "Title", "Shop", ["- x"])
    one = packager.package(prod, tmp_path / "dist", "SKU", max_mb=5)
    assert len(one) == 1
    parts = packager.package(prod, tmp_path / "dist", "SKU", max_mb=0.9)
    assert len(parts) == 2
    for z in parts:
        assert validate.check_zip(z, 0.9)["ok"]
        assert "prod/LICENSE.txt" in zipfile.ZipFile(z).namelist()


# ------------------------------------------------------------ end to end
def test_build_job_end_to_end(small_sizes):
    types = ["welcome_screen", "strip_2x6", "overlay_4x6", "gif_overlay", "buttons"]
    jid = db.add_job("Glam Birthday Bash", "Pastel Party", types, 2, small_sizes, seed=5)
    pid = pipeline.build_job(jid, log=lambda *a: None)
    p = db.get_product(pid)
    assert p["valid"] == 1, p["validation"]
    assert p["status"] == "draft"
    root = Path(p["bundle_dir"])
    assert (root / "listing" / "listing.json").exists()
    rep = json.loads((root / "validation.json").read_text())
    assert rep["files_ok"] == rep["files_checked"] > 20
    assert sorted(p["zip_files"]) == [f"dist/etsy/{p['sku']}.zip", f"dist/shopify/{p['sku']}.zip"]
    names = zipfile.ZipFile(root / p["zip_files"][0]).namelist()
    assert any("03_Photo_Strips_2x6" in n and n.endswith("_blank.png") for n in names)
    assert any("button_start" in n for n in names)
    assert db.get_job(jid)["status"] == "done"
    assert db.one("SELECT COUNT(*) n FROM costs WHERE product_id=?", (pid,))["n"] == 1


def test_blocked_theme_job_fails():
    jid = db.add_job("Minecraft Birthday", "Pastel Party", ["buttons"], 1)
    assert pipeline.build_job(jid, log=lambda *a: None) is None
    assert db.get_job(jid)["status"] == "failed"
    assert db.one("SELECT COUNT(*) n FROM errors WHERE job_id=?", (jid,))["n"] == 1


def test_add_variations_keeps_sku_and_status(small_sizes):
    jid = db.add_job("Modern Corporate Gala", "Navy & Gold", ["overlay_4x6"], 1, small_sizes, seed=9)
    pid = pipeline.build_job(jid, log=lambda *a: None)
    db.set_product_status(pid, "approved")
    sku = db.get_product(pid)["sku"]
    pid2 = pipeline.add_variations(pid, 2, log=lambda *a: None)
    p = db.get_product(pid2)
    assert pid2 == pid and p["sku"] == sku and p["status"] == "approved" and len(p["palettes"]) == 3
