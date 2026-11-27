"""Phase 2: animated welcome screens, preview mockups, marketing content."""
import json
import subprocess
from pathlib import Path

from PIL import Image

from studio import animate, db, pipeline, render, themes, validate
from studio.palettes import parse_palette, smart_title


def design(theme="Winter Holiday Party"):
    prof = themes.resolve(theme)
    return render.Design(theme, prof, 3, prof["headlines"][0], prof["placeholder"])


def frame(path, n):
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})",
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True)
    return out.stdout


def test_welcome_video_valid_and_seamless(tmp_path):
    p = animate.welcome_video(design(), parse_palette("Navy & Gold"), tmp_path / "v.mp4", (320, 180), seconds=2, fps=15)
    res = validate.check_video(p, (320, 180), min_seconds=1.5)
    assert res["ok"], res["issues"]
    first, last, mid = frame(p, 0), frame(p, 29), frame(p, 15)
    diff = lambda a, b: sum(abs(x - y) for x, y in zip(a, b)) / len(a)
    # last frame flows into the first (loop) and the middle frame actually moves
    assert diff(first, last) < diff(first, mid)
    assert diff(first, mid) > 0.3


def test_smart_title():
    assert smart_title("gatsby new year's eve") == "Gatsby New Year's Eve"


def test_full_bundle_with_previews_and_marketing(small_sizes):
    jid = db.add_job("Pastel Baby Shower", "Lavender Dream", list(small_sizes), 2, small_sizes, seed=4)
    pid = pipeline.build_job(jid, log=lambda *a: None)
    p = db.get_product(pid)
    assert p["valid"] == 1, p["validation"]["errors"]
    root = Path(p["bundle_dir"])
    previews = sorted(x.name for x in (root / "previews").iterdir() if x.is_file())
    assert previews == ["01_hero.jpg", "02_color_variations.jpg", "03_print_templates.jpg",
                        "04_gif_and_buttons.jpg", "05_whats_included.jpg", "06_gif_overlay_preview.gif"]
    assert Image.open(root / "previews" / "01_hero.jpg").size == (2400, 1800)
    mk = root / "marketing"
    assert Image.open(mk / "pinterest_pin_1000x1500.png").size == (1000, 1500)
    assert len(list(mk.glob("instagram_carousel_*.png"))) == 5
    assert validate.check_video(mk / "tiktok_reel_1080x1920.mp4", (1080, 1920))["ok"]
    kit = json.loads((mk / "captions.json").read_text())
    assert kit["status"].startswith("DRAFT")
    assert not themes.find_blocked(json.dumps(kit))
    videos = list((root / "product").rglob("*.mp4"))
    assert len(videos) == 2  # one per color variation
