# @thelayahedit — Walmart Finds Video Generator

Turns a simple config file + your product photos (+ your voiceover) into
**three 1080×1920 vertical MP4s** (20–30 s) in a cream / blush / beige / black style.

| Variation | Look | Hook style | Transitions |
|---|---|---|---|
| `editorial` | Cream paper, serif headlines | Words rise in, product cards fan out, hand-drawn underline | Soft rise + fade |
| `checklist` | Blush, bold sans | Checklist of every product with live check-marks and prices | Beige panel wipe with the product number |
| `bold` | Black + cream type | Uppercase words slam in, products fly in | Whip pan with motion blur |

Each video has: an animated hook from frame 0 (in motion before 2 s), an **always-visible
affiliate disclosure**, a full disclosure card during a **reserved audible-disclosure slot**,
product spotlights (push-in zoom, swinging price tag, kinetic product name, feature chips,
"price as of" date), word-highlighted captions, and the end card
**"Shop my Walmart finds — link in bio."** There's **no music**. Every file has a silent
audio track (or your voiceover) so you can add your own licensed music in CapCut, TikTok, etc.

Sample renders are in [`samples/`](samples/).

---

## 1. One-time setup

You need Python 3.9+ and FFmpeg.

```bash
# macOS:   brew install ffmpeg python
# Windows: winget install ffmpeg   (and install Python from python.org)
cd walmart-finds-video
pip install -r requirements.txt
# optional, for the most accurate caption sync:
pip install faster-whisper
```

## 2. Make videos

```bash
python make_videos.py config/walmart_finds_nov2026.yaml
```
Videos go to `output/`. For each variation you get the `.mp4`, a `_cover.png` (a thumbnail
frame), and an `.srt` caption file you can upload to TikTok/YouTube.

Useful options:
```bash
python make_videos.py CONFIG --script                 # print the voiceover script to read
python make_videos.py CONFIG -v bold                  # just one variation
python make_videos.py CONFIG --voiceover voiceover/take1.m4a
python make_videos.py CONFIG --stills 0.5,6,12        # quick PNG previews (seconds)
```

## 3. Add your voiceover (captions sync automatically)

1. Run `python make_videos.py CONFIG --script` and record yourself reading it on your
   phone (Voice Memos is fine). **Pause briefly (about half a second) between sections.** The
   generator uses those pauses to line each product up with your voice.
2. Save the file in `voiceover/` (m4a, mp3 and wav all work).
3. Either put the path under `voiceover: file:` in the config, or pass `--voiceover`.

The video length then follows your voice, each product appears just as you start talking
about it, and the captions highlight word by word. Your audio is loudness-normalised to
-16 LUFS (turn that off with `normalize_loudness: false`). If you read slightly
differently from the script, that's fine. If `faster-whisper` is installed it listens for
the exact word timing. Without it, timing comes from where you speak and where you pause.
If the take runs over 30 s, you'll get a warning.

**Audible disclosure:** the line under `disclosure: audible_script` is part of the script,
right after the hook. The on-screen disclosure card shows during that slot.

## 4. Add new products / make a new video

1. Put the product image in `assets/products/`. Use the official image from the Walmart
   listing or the brand's media kit, which you're allowed to use. PNG or JPG, 1000 px or
   larger is best. The generator only scales and moves images. It never recolors, crops,
   warps or retouches them, and no text or price tag ever covers the photo.
2. Copy the config: `cp config/walmart_finds_nov2026.yaml config/dog_finds_dec2026.yaml`
3. Edit the `products:` list:

```yaml
  - id: dog-bed                       # any short id
    name: "Full product name as listed on Walmart"
    short_name: "Calming Dog Bed"     # big headline (2-4 words)
    category: "Dog essentials"
    image: assets/products/dog-bed.png
    price: 24.97                      # exactly what Walmart shows
    price_verified_on: 2026-12-05     # the date you checked it
    # was_price: 39.99                # ONLY if Walmart shows a "was" price,
    # was_price_shown_on_walmart: true  # and then also set this line
    features: ["Machine washable", "Medium size"]   # facts from the listing, max 4
    voiceover: "This calming dog bed is $24.97."
```

4. Update `slug:`, `hook_voiceover:` and the `variations:` hooks if you like, then run
   `python make_videos.py config/dog_finds_dec2026.yaml`.

**Tips:** 3 products fit 20–30 s best (1–5 are supported). Keep `short_name` short.

### Hooks stay true automatically
In variation hooks you can use `{count}`, `{count_word}`, `{under_price}`, `{max_price}`
and `{min_price}`. They're calculated from your verified prices. For example
"under {under_price}" becomes "under $35" when the most expensive item is $34.00, and it
updates itself if prices change. Wrap a word in `*asterisks*` to highlight it.

### Built-in honesty guards
- A price without a verification date stops the render.
- A `was_price` is ignored unless you confirm Walmart shows it, and it has to be higher than the price.
- You get a warning if a voiceover line says a dollar amount that doesn't match the product's price.
- The video never adds ratings, reviews, "I tried this", demos or savings percentages.
  Only add claims like that to your script if they're true for you.

## 5. AI-generated backgrounds (optional)

By default the backgrounds are drawn in code (soft gradients, light blobs, film grain).
These aren't AI-generated, so they aren't labelled. To use an AI-generated background:

1. Make one with your image tool (see prompts in `assets/backgrounds/PROMPTS.md`) in
   portrait 9:16 or larger, and save it in `assets/backgrounds/`.
2. Set it on a variation: `ai_background: assets/backgrounds/cream_linen.png`

The image is softened with the brand palette so products stay the focus, and a visible
**"AI-generated background"** label is added automatically (change the wording with
`ai_background_label`). AI is never used on the product images.

## 6. Change the look

- Colors: `finds/looks.py` (`CREAM`, `BLUSH`, `BEIGE`, `BLACK` and each look's settings)
- Fonts: `assets/fonts/` (DM Serif Display + Inter, both under the SIL Open Font License)
- Scene layout and animation: `finds/scenes.py`
- Scene lengths without a voiceover: `finds/timeline.py` (`HOOK_S`, `DISCLOSURE_S`, `CTA_S`)
- The disclosure, CTA, handle and caption options are all in the config file.

## Project layout
```
make_videos.py          command line
config/*.yaml           one file per video (products, prices, script, hooks)
assets/products/        your product images
assets/backgrounds/     optional AI backgrounds + PROMPTS.md
assets/fonts/           bundled fonts
voiceover/              your recordings
finds/                  the engine (config, timeline, captions, scenes, looks, render)
output/                 rendered videos (not committed)
samples/                example renders
```

> The demo product images in `assets/products/` were cropped from phone screenshots of the
> Walmart app (the Beats image had its top padded where the app header cut it off). Replace
> them with the full-resolution official images before you post.
