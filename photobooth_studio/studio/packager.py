"""Packages the customer-facing files into marketplace-ready ZIP files.

Most marketplaces cap each digital file (Etsy: 20 MB, 5 files). When a bundle
is larger it is split by color variation automatically.
"""
from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path

LICENSE_TXT = """LICENSE - {shop}

Thank you for your purchase!

YOU MAY
- Use these designs at unlimited events for your own photo booth business.
- Add your clients' names, dates and text to the designs.
- Print the designs and display the screens at your clients' events.

YOU MAY NOT
- Resell, share, give away or redistribute the files (edited or unedited).
- Claim the artwork as your own design or upload it to template marketplaces.

All artwork is original. Fonts used are licensed under the SIL Open Font
License (commercial use permitted).
"""

README_TXT = """{title}
SKU: {sku}

START HERE
==========
Folders are organised by product type, then by color variation.
Each print design comes in two versions:
  *_text.png  - with sample headline and placeholder text
  *_blank.png - artwork only, so you can add your own names / date

Transparent areas (checkerboard in most editors) are where guest photos go.

SIZES
{sizes}

TIPS
- Load PNG overlays as "overlay / template" layers in your booth software.
- 2x6 strips: use the 4x6 double-strip sheet if your printer cuts 4x6 into two strips.
- Welcome videos are seamless loops (H.264 MP4) - set your start screen to loop.
- Buttons have transparent backgrounds and can be resized down without losing quality.

Need help? Contact {shop} through the marketplace messages.
"""


def write_docs(product_dir: Path, sku, title, shop, sizes_lines):
    (product_dir / "README_START_HERE.txt").write_text(
        README_TXT.format(title=title, sku=sku, shop=shop, sizes="\n".join(sizes_lines)), encoding="utf-8")
    (product_dir / "LICENSE.txt").write_text(LICENSE_TXT.format(shop=shop), encoding="utf-8")


def _zip(files: list[Path], root: Path, out: Path, extra: list[Path]):
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in extra + files:
            z.write(f, f.relative_to(root.parent))
    return out


def package(product_dir: Path, dist_dir: Path, sku: str, max_mb: float) -> list[Path]:
    """Create one ZIP, or several (split by variation) if over max_mb."""
    for old in dist_dir.glob("*.zip"):
        old.unlink()
    docs = [product_dir / "README_START_HERE.txt", product_dir / "LICENSE.txt"]
    files = sorted(p for p in product_dir.rglob("*") if p.is_file() and p not in docs)
    total = sum(f.stat().st_size for f in files)
    limit = max_mb * 1e6 * 0.97
    # PNG/MP4 barely compress, so raw size is a good estimate of the ZIP size.
    if total <= limit:
        return [_zip(files, product_dir, dist_dir / f"{sku}.zip", docs)]

    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        rel = f.relative_to(product_dir).parts
        groups[rel[1] if len(rel) > 2 else "shared"].append(f)
    parts: list[list[Path]] = []
    cur, cur_size = [], 0
    for _, gfiles in sorted(groups.items()):
        gsize = sum(f.stat().st_size for f in gfiles)
        if cur and cur_size + gsize > limit:
            parts.append(cur)
            cur, cur_size = [], 0
        if gsize > limit:  # one variation alone is too big: split it by file
            for f in gfiles:
                if cur and cur_size + f.stat().st_size > limit:
                    parts.append(cur)
                    cur, cur_size = [], 0
                cur.append(f)
                cur_size += f.stat().st_size
        else:
            cur += gfiles
            cur_size += gsize
    if cur:
        parts.append(cur)
    return [_zip(p, product_dir, dist_dir / f"{sku}_part{i + 1}of{len(parts)}.zip", docs)
            for i, p in enumerate(parts)]
