# Photo Booth Studio

An automated production system for digital products sold to **photo booth
business owners**. It runs on your own computer, overnight, and produces
**draft** product bundles plus marketing material for you to review in the
morning.

It never publishes listings, posts to social media, sends messages, buys
anything or spends money. You approve every product and upload it yourself.

## What it makes

For each theme (e.g. *"Rustic Boho Wedding"*) and color palette:

| Product | Default size | Format |
|---|---|---|
| Welcome screen | 1920×1080 | PNG |
| Animated welcome screen (seamless loop) | 1920×1080, 8 s | MP4 (H.264) |
| 2×6 photo strip (+ 4×6 double-strip print sheet) | 600×1800 @ 300 DPI | PNG, transparent photo windows |
| 4×6 print overlay | 1800×1200 @ 300 DPI | PNG, transparent photo window |
| GIF / boomerang overlay | 1080×1080 | PNG, transparent photo window |
| Experience buttons (Start, Photo, GIF, Boomerang, Video, Retake, Print, Share, Done) | 800×260 | PNG, transparent |

You also get:

- **Color variations**: the same layout re-colored automatically, with names like *Aqua Noir* or *Lavender*.
- **Text and blank versions** of every print design, so buyers can add their own names and dates.
- **Listing preview images**: 6 mockups at 2400×1800, including a hero mockup with a tablet and prints, a colors grid, print templates, GIF overlays with buttons, a "what's included" image and an animated GIF.
- **Store-ready ZIPs for Etsy and/or Shopify**: Etsy ZIPs split automatically at 20 MB, and Shopify gets one ZIP per bundle. Each ZIP has a README and a buyer license.
- **Listing copy**: a title of 140 characters or fewer, a description, 13 Etsy tags of 20 characters or fewer, a suggested price, and estimated fees and take-home for each store.
- **Shopify extras**: square 2048×2048 photos, an SEO title and description, a URL handle, an HTML description, and a product import CSV that creates the product as an unpublished draft.
- **Marketing drafts**:
  - a Pinterest pin (1000×1500)
  - an Instagram carousel (5 slides, 1080×1350)
  - a TikTok/Reels video (1080×1920)
  - captions, hashtags and a TikTok script
- **An inventory database** (SQLite) holding products, files, validation results, runs, errors, costs and sales.
- **A daily report** listing completed products, errors, money and recommended next steps.

## Setup (about 5 minutes)

You need **Python 3.10+** and **ffmpeg**. Both are free.

| OS | Install |
|---|---|
| macOS | `brew install python ffmpeg` (Homebrew: https://brew.sh) |
| Windows | Python from https://python.org (tick "Add to PATH"); ffmpeg: `winget install ffmpeg` |
| Linux | `sudo apt install python3 python3-venv ffmpeg` |

Then, in this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                # optional: runs the test suite (~2 min)
```

## Daily use

### 1. Open the dashboard

```bash
python -m studio dashboard          # or double-click scripts/start_dashboard.bat on Windows
```

Open **http://127.0.0.1:8765**. The dashboard is only reachable from your own computer.

- **New product bundle**: enter a theme, pick a preset palette or your own four colors (background, primary, accent, text), tick the product types, adjust pixel dimensions if needed, then choose:
  - **Add to overnight queue**: built tonight.
  - **Build now**: builds right away. A full bundle with 4 colors takes about 1–2 minutes.
- **Product page**:
  - Review the previews, the animated screen, the listing copy, the validation results and the marketing drafts.
  - Then click **Approve** or **Reject**.
  - **Add more color variations** re-renders an approved design with extra colors.
  - Once you have uploaded it to your shop yourself, click **Mark as listed**.
- **Sales & costs**: import your sales CSV and record costs such as listing fees or ads. The store is detected automatically.
  - **Etsy**: *Shop Manager → Settings → Options → Download Data → Sold Order Items*.
  - **Shopify**: *Orders → Export*. Refunded and pending orders are skipped, and card fees are estimated from your settings because Shopify's export doesn't include them.
- **Daily report**: what was built, errors, profit and next steps.

### 2. Turn on the overnight workflow

macOS / Linux (runs nightly at 01:30; pass hour and minute to change it):

```bash
./scripts/install_schedule_mac_linux.sh        # e.g. ./scripts/install_schedule_mac_linux.sh 2 15
```

Windows: double-click `scripts\install_schedule_windows.bat`.

Each night the workflow:

1. Builds the queued jobs, up to `max_bundles_per_night` (default 2).
2. If the queue is short and **autopilot** is on, picks original themes for upcoming seasons, 8 weeks ahead (e.g. holiday parties in November, Valentine's Day in December), then evergreen themes such as weddings and birthdays. It never repeats a theme.
3. Validates every file, then writes `output/reports/YYYY-MM-DD.md`.

Your computer must be awake at that time. To run the workflow by hand: `python -m studio overnight`.

### 3. Morning review → listing (manual, by you)

1. Open the dashboard and review each draft.
2. Approve the good ones.
3. Open the product's folder in `output/bundles/<SKU>/` and follow the steps for your store below.
4. Click **Mark as listed**.

**Etsy**

- Upload every ZIP in `dist/etsy/` as the digital files.
- Use the photos in `previews/*.jpg`, in order.
- Use `marketing/tiktok_reel_1080x1920.mp4` as the listing video.
- Paste the title, tags, description and price from `listing/listing.md`.

**Shopify**

1. Install a digital delivery app once, for example Shopify's free *Digital Downloads* app.
2. Go to **Products → Import** and choose `listing/shopify_product_import.csv`. For several products at once, use **Inventory → Export approved products to a Shopify import CSV**, or run `python -m studio shopify-csv`. Products are created as **drafts**: unpublished, with no shipping, and with the SEO fields filled in.
3. Open the draft product and add the photos from `previews/square/`.
4. Attach `dist/shopify/*.zip` in your digital downloads app.
5. Publish it yourself when you're ready.

`marketing/` holds the social media drafts. Post them when you choose.

## Command line

```bash
python -m studio build --theme "Gatsby New Year's Eve" --palette "Black & Gold"           # build now
python -m studio build --theme "Sage Garden Bridal Shower" --palette "#F3F5EE,#8FA98B,#C8A96A,#334433" \
       --types strip_2x6,overlay_4x6 --variations 3 --size overlay_4x6=1200x1800 --queue   # queue for tonight
python -m studio list                     # inventory
python -m studio status 3 approved        # draft | approved | rejected | listed | retired
python -m studio variations 3 --extra 2   # add color variations to product 3
python -m studio presets                  # palette presets
python -m studio overnight                # run the nightly workflow now
python -m studio report                   # write today's report
python -m studio import-sales orders.csv  # import sales CSV (Etsy or Shopify, detected automatically)
python -m studio shopify-csv              # Shopify import CSV for all approved products
python -m studio cost advertising 5.00 --note "Pinterest promo"
```

## Settings: `config/settings.json`

| Key | Meaning |
|---|---|
| `shop_name` | Printed in the buyer README, buyer license and Pinterest pin |
| `default_variations` | Colors per bundle (default 4) |
| `max_bundles_per_night` | Overnight limit |
| `autopilot` | `true` lets the workflow choose seasonal themes when the queue is empty; `false` makes it build only what you queue |
| `video_seconds`, `video_fps` | Animated welcome screen length |
| `preview_watermark` | Faint "PREVIEW" watermark on listing images |
| `stores` | `["etsy"]`, `["shopify"]` or both (the default). Controls which ZIPs, images, copy and import files are made |
| `store_settings` | For each store: ZIP size limit (`max_zip_mb`) and fees. Shopify card fees depend on your plan; update `payment_pct` and `payment_fixed` to match yours |
| `pricing` | Component prices, bundle discount, uplift per extra color, min/max price |
| `compute_cost_per_hour` | Electricity cost estimate per render-hour (logged automatically) |
| `blocked_terms_extra` | Your own additions to the trademark blocklist |

## Licensing & safety

- **Artwork** is 100% procedural. Leaves, confetti, balloons, stars, snowflakes, frames and sample silhouettes are drawn from geometry in code. No clip art, stock photos or AI image models are used, so there is nothing third-party to license.
- **Fonts** (`assets/fonts/`) are Google Fonts under the **SIL Open Font License**: Great Vibes, Pacifico, Playfair Display, Montserrat and Cinzel. The OFL allows commercial use and embedding in sold designs. The license files are included.
- **Trademark and character guard**: themes, titles, descriptions and tags are checked against a blocklist of brands, franchises, characters and celebrities. Blocked themes are refused. You can add your own terms in settings.
- **No customer branding**: designs use generic placeholders ("Names Here • 00.00.2027"), and blank versions are included.
- **Validation**: every file is checked before packaging:
  - dimensions and DPI
  - transparency, including that each photo window is actually see-through
  - not blank, not corrupt
  - video codec, pixel format and duration
  - ZIP integrity and size limit
  - listing rules: title length, tag count and length, blocked terms
- **No outbound actions**: the code has no network clients. A test (`test_no_publishing_code`) fails if one is ever added.

## Costs

Everything is free and open source: Python, Pillow, NumPy, ffmpeg, SQLite and OFL fonts. There are no AI API calls. Rendering is deterministic, so the same seed always gives the same design. The only recurring cost is electricity, which is estimated and logged per render.

## Project layout

```
studio/
  config.py      product specs & paths          palettes.py  colors, variations, contrast
  themes.py      style profiles + trademark guard   motifs.py  procedural artwork
  render.py      static product renderers       animate.py   looping MP4 welcome screens
  previews.py    listing mockups                marketing.py social drafts & captions
  listing.py     titles/descriptions/tags/price packager.py   ZIPs + buyer README/license
  stores.py      Etsy/Shopify limits, fees, SEO, Shopify import CSV
  validate.py    file & listing validation      pipeline.py  builds one bundle from a job
  db.py          SQLite inventory               scheduler.py overnight workflow + autopilot
  sales.py       CSV sales import & summaries   report.py    daily report
  dashboard.py   local web dashboard            cli.py       command line
scripts/         schedule installers, launchers
tests/           test_phase1.py (core), test_phase2.py (media), test_phase3.py (automation), test_shopify.py
output/          generated bundles, reports, logs, database (git-ignored)
```

## Roadmap (next phases)

- **Phase 4**:
  - more layout families: split-screen welcome screens, 4-photo strips, portrait 4×6 collages
  - more motif packs
  - a print-preview proof sheet
- **Phase 5**: optional AI copywriting. This would be off by default and capped by a budget setting you approve.
- **Phase 6**: optional uploads to Etsy, Shopify and social media through their APIs, created as **drafts** that you confirm one by one.
