"""File validation: every generated file is checked before it can be packaged."""
from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from .themes import find_blocked


def check_image(path: Path, expect_size=None, transparent=None, dpi=None, windows=None) -> dict:
    issues = []
    info = {"path": str(path), "ok": False, "issues": issues}
    if not path.exists() or path.stat().st_size == 0:
        issues.append("missing or empty file")
        return info
    info["bytes"] = path.stat().st_size
    try:
        with Image.open(path) as im:
            im.verify()
        im = Image.open(path)
        im.load()
    except Exception as e:  # corrupt
        issues.append(f"cannot open: {e}")
        return info
    info["width"], info["height"] = im.size
    if expect_size and tuple(im.size) != tuple(expect_size):
        issues.append(f"size {im.size} != expected {tuple(expect_size)}")
    if dpi:
        got = im.info.get("dpi")
        if not got or round(got[0]) != dpi:
            issues.append(f"dpi {got} != {dpi}")
    arr = np.asarray(im.convert("RGBA"))
    if transparent is True:
        if im.mode != "RGBA":
            issues.append(f"mode {im.mode} has no transparency")
        elif (arr[..., 3] == 0).mean() < 0.05:
            issues.append("expected transparent photo area(s) but <5% of pixels are transparent")
    if transparent is False and im.mode == "RGBA" and (arr[..., 3] < 255).any():
        issues.append("unexpected transparency")
    for (x0, y0, x1, y1) in windows or []:
        cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)
        if arr[cy, cx, 3] != 0:
            issues.append(f"photo window center ({cx},{cy}) not transparent")
    rgb = arr[..., :3][arr[..., 3] > 0]
    if rgb.size and rgb.std() < 3:
        issues.append("image looks blank (no visible detail)")
    info["ok"] = not issues
    return info


def check_video(path: Path, expect_size=None, min_seconds=2.0) -> dict:
    issues = []
    info = {"path": str(path), "ok": False, "issues": issues}
    if not path.exists() or path.stat().st_size == 0:
        issues.append("missing or empty file")
        return info
    info["bytes"] = path.stat().st_size
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,codec_name,pix_fmt:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, check=True).stdout
        meta = json.loads(out)
        st = meta["streams"][0]
        info["width"], info["height"] = st["width"], st["height"]
        dur = float(meta["format"]["duration"])
        info["duration"] = dur
        if expect_size and (st["width"], st["height"]) != tuple(expect_size):
            issues.append(f"size {(st['width'], st['height'])} != {tuple(expect_size)}")
        if st["codec_name"] not in ("h264", "gif"):
            issues.append(f"codec {st['codec_name']}")
        if st["codec_name"] == "h264" and st.get("pix_fmt") != "yuv420p":
            issues.append(f"pix_fmt {st.get('pix_fmt')} (yuv420p needed for compatibility)")
        if dur < min_seconds:
            issues.append(f"duration {dur:.1f}s too short")
    except Exception as e:
        issues.append(f"ffprobe failed: {e}")
    info["ok"] = not issues
    return info


def check_zip(path: Path, max_mb: float) -> dict:
    issues = []
    info = {"path": str(path), "ok": False, "issues": issues}
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                issues.append(f"corrupt member {bad}")
            info["members"] = len(z.namelist())
    except Exception as e:
        issues.append(f"bad zip: {e}")
        return info
    mb = path.stat().st_size / 1e6
    info["bytes"] = path.stat().st_size
    if mb > max_mb:
        issues.append(f"{mb:.1f} MB exceeds marketplace limit {max_mb} MB")
    info["ok"] = not issues
    return info


def check_listing(listing: dict) -> list[str]:
    issues = []
    text = " ".join([listing.get("title", ""), listing.get("description", ""), " ".join(listing.get("tags", []))])
    hits = find_blocked(text)
    if hits:
        issues.append(f"blocked trademark/character terms: {', '.join(hits)}")
    if len(listing.get("title", "")) > 140:
        issues.append("title longer than 140 characters")
    tags = listing.get("tags", [])
    if len(tags) > 13:
        issues.append("more than 13 tags")
    for t in tags:
        if len(t) > 20:
            issues.append(f"tag over 20 chars: {t}")
    if not listing.get("price") or listing["price"] <= 0:
        issues.append("missing price")
    sh = listing.get("shopify")
    if sh:
        if len(sh["seo_title"]) > 70:
            issues.append("Shopify SEO title over 70 characters")
        if len(sh["seo_description"]) > 320:
            issues.append("Shopify SEO description over 320 characters")
        if not re.fullmatch(r"[a-z0-9-]+", sh["handle"]):
            issues.append(f"bad Shopify handle: {sh['handle']}")
        hits = find_blocked(" ".join([sh["seo_title"], sh["seo_description"], " ".join(sh["tags"])]))
        if hits:
            issues.append(f"blocked terms in Shopify fields: {', '.join(hits)}")
    return issues
