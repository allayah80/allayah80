"""Overnight workflow: process the queue, optionally top up with seasonal
autopilot ideas, then write the daily report.

Safety: this module only creates DRAFT files on your computer. It contains no
code that publishes listings, posts to social media, sends messages or spends
money.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db, pipeline
from .config import PRODUCT_TYPES, load_settings, out_dirs

# (month, day) of the event peak, theme, palette
SEASONAL = [
    ((2, 14), "Blush Valentine's Day Party", "Blush & Gold"),
    ((2, 14), "Galentine's Brunch", "Pastel Party"),
    ((4, 20), "Spring Garden Party", "Sage Garden"),
    ((5, 25), "Class of 2027 Graduation", "Navy & Gold"),
    ((5, 25), "Modern Graduation Party", "Black & Gold"),
    ((7, 1), "Tropical Summer Luau", "Ocean Breeze"),
    ((10, 31), "Spooky Halloween Bash", ["#1A1423", "#F28C28", "#7B4BA8", "#F7F3E8"]),
    ((12, 20), "Winter Wonderland Holiday Party", "Silver Frost"),
    ((12, 20), "Merry and Bright Christmas", "Burgundy Rose"),
    ((12, 15), "Corporate Holiday Party", "Emerald Luxe"),
    ((12, 31), "Gatsby New Year's Eve", "Black & Gold"),
    ((12, 31), "Disco New Year Party", "Neon Night"),
]

EVERGREEN = [
    ("Elegant Floral Wedding", "Blush & Gold"),
    ("Rustic Boho Wedding", "Terracotta Boho"),
    ("Modern Minimal Wedding", "Black & Gold"),
    ("Glam 30th Birthday", "Black & Gold"),
    ("Pastel Birthday Party", "Pastel Party"),
    ("Sweet Baby Shower", "Lavender Dream"),
    ("Corporate Gala Night", "Navy & Gold"),
    ("Quinceanera Celebration", "Lavender Dream"),
    ("Anniversary Celebration", "Burgundy Rose"),
    ("Emerald Engagement Party", "Emerald Luxe"),
]


def upcoming_seasons(today: date | None = None, weeks: int = 8):
    """Seasonal ideas whose event date falls within the next `weeks` weeks."""
    today = today or date.today()
    out = []
    for (m, d), theme, pal in SEASONAL:
        ev = date(today.year, m, d)
        if ev < today:
            ev = date(today.year + 1, m, d)
        days = (ev - today).days
        if days <= weeks * 7:
            out.append({"theme": theme, "palette": pal, "event_date": ev.isoformat(), "days_away": days})
    return sorted(out, key=lambda x: x["days_away"])


def _already_made(theme: str) -> bool:
    return bool(db.one("SELECT id FROM jobs WHERE lower(theme)=lower(?) AND status IN ('queued','running','done')",
                       (theme,)))


def autopilot_ideas(n: int, today: date | None = None) -> list[dict]:
    st = load_settings()
    ideas = []
    for s in upcoming_seasons(today, st.get("autopilot_lead_weeks", 8)):
        if not _already_made(s["theme"]):
            ideas.append(s)
    for theme, pal in EVERGREEN:
        if not _already_made(theme):
            ideas.append({"theme": theme, "palette": pal})
    return ideas[:n]


# ---------------------------------------------------------------- locking
def _lock_path() -> Path:
    return out_dirs()["base"] / "overnight.lock"


def acquire_lock(max_age_h=6) -> bool:
    p = _lock_path()
    if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
        return False
    p.write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        _lock_path().unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- main
def run_overnight(max_jobs: int | None = None, autopilot: bool | None = None, log=print) -> int:
    st = load_settings()
    max_jobs = max_jobs or st.get("max_bundles_per_night", 2)
    autopilot = st.get("autopilot", True) if autopilot is None else autopilot
    if not acquire_lock():
        log("Another overnight run is in progress (lock file present). Exiting.")
        return 1
    run_id = db.start_run("overnight")
    t0 = time.process_time()
    made, errors = 0, 0
    try:
        log(f"[{datetime.now():%Y-%m-%d %H:%M}] Overnight run #{run_id} started")
        queued = db.rows("SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT ?", (max_jobs,))
        job_ids = [j["id"] for j in queued]
        if autopilot and len(job_ids) < max_jobs:
            for idea in autopilot_ideas(max_jobs - len(job_ids)):
                jid = db.add_job(idea["theme"], idea["palette"] if isinstance(idea["palette"], str) else
                                 ",".join(idea["palette"]), PRODUCT_TYPES, st["default_variations"],
                                 source="autopilot")
                log(f"  autopilot queued: {idea['theme']}")
                job_ids.append(jid)
        if not job_ids:
            log("  Queue empty and autopilot off - nothing to build.")
        for jid in job_ids:
            pid = pipeline.build_job(jid, run_id, log)
            if pid:
                made += 1
                p = db.get_product(pid)
                errors += len(p["validation"].get("errors", []))
            else:
                errors += 1
    except Exception as e:  # never crash silently overnight
        errors += 1
        db.log_error("overnight", str(e), run_id)
        log(f"  ! overnight error: {e}")
    finally:
        db.finish_run(run_id, made, errors, time.process_time() - t0)
        release_lock()
    from . import report
    path = report.daily_report()
    log(f"Done: {made} draft bundle(s), {errors} issue(s). Report: {path}")
    return 0
