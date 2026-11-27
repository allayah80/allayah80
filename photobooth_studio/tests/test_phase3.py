"""Phase 3: overnight scheduler, sales/costs, daily report, dashboard."""
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import pytest

from studio import dashboard, db, report, sales, scheduler
from studio.config import out_dirs


# ------------------------------------------------------------ scheduler
def test_upcoming_seasons_window():
    s = scheduler.upcoming_seasons(date(2026, 11, 27), weeks=8)
    themes = [x["theme"] for x in s]
    assert "Gatsby New Year's Eve" in themes and "Spooky Halloween Bash" not in themes
    assert all(x["days_away"] <= 56 for x in s)
    s2 = scheduler.upcoming_seasons(date(2027, 1, 5), weeks=8)  # wraps into next year correctly
    assert any(x["theme"].startswith("Blush Valentine") for x in s2)


def test_autopilot_skips_already_made():
    first = scheduler.autopilot_ideas(3, date(2026, 11, 27))
    assert len(first) == 3
    db.add_job(first[0]["theme"], "Black & Gold", ["buttons"], 1)
    second = scheduler.autopilot_ideas(3, date(2026, 11, 27))
    assert first[0]["theme"] not in [x["theme"] for x in second]


def test_overnight_runs_queue_and_writes_report(small_sizes):
    jid = db.add_job("Starry Graduation Night", "Navy & Gold", ["overlay_4x6", "buttons"], 1, small_sizes, seed=2)
    bad = db.add_job("Pokemon Party", "Pastel Party", ["buttons"], 1)
    logs = []
    assert scheduler.run_overnight(max_jobs=5, autopilot=False, log=logs.append) == 0
    assert db.get_job(jid)["status"] == "done"
    assert db.get_job(bad)["status"] == "failed"
    run = db.one("SELECT * FROM runs ORDER BY id DESC")
    assert run["products_made"] == 1 and run["errors"] >= 1 and run["finished_at"]
    rpt = (out_dirs()["reports"] / f"{date.today().isoformat()}.md").read_text()
    assert "Starry Graduation Night" in rpt and "pokemon" in rpt.lower()
    assert "Nothing was published" in rpt
    assert not (out_dirs()["base"] / "overnight.lock").exists()


def test_overnight_lock_prevents_double_run():
    assert scheduler.acquire_lock()
    try:
        assert scheduler.run_overnight(autopilot=False, log=lambda *a: None) == 1
    finally:
        scheduler.release_lock()


def test_no_publishing_code():
    """Guardrail: the codebase must not contain network/posting clients."""
    import pathlib
    src = " ".join(p.read_text() for p in pathlib.Path(scheduler.__file__).parent.glob("*.py"))
    for forbidden in ("requests.post", "urlopen", "smtplib", "http.client", "boto3", "openai", "anthropic"):
        assert forbidden not in src, forbidden


# ------------------------------------------------------------ sales & costs
ETSY_CSV = """Sale Date,Item Name,Buyer,Quantity,Price,Coupon Code,Order ID,Transaction ID,SKU
11/20/26,Neon Bundle,x,1,$14.99,,1001,1,PB261120-0001
11/21/26,Neon Bundle,y,2,$29.98,,1002,2,PB261120-0001
11/22/26,Other Thing,z,1,5.00,,1003,3,
"""


def test_sales_import_and_dedupe():
    added, skipped = sales.import_text(ETSY_CSV)
    assert (added, skipped) == (3, 0)
    added, skipped = sales.import_text(ETSY_CSV)
    assert (added, skipped) == (0, 3)
    s = sales.summary(None)
    assert s["orders"] == 3 and abs(s["revenue"] - 49.97) < 1e-6 and s["units"] == 4
    assert sales.top_sellers()[0]["item"] == "PB261120-0001"


def test_sales_import_rejects_unknown_csv():
    with pytest.raises(ValueError):
        sales.import_text("a,b\n1,2\n")


def test_costs_in_profit():
    sales.import_text(ETSY_CSV)
    db.add_cost("listing fees", 0.60, "3 listings")
    s = sales.summary(None)
    assert abs(s["profit"] - (49.97 - 0.60)) < 1e-6


def test_report_recommendations_without_data():
    d = report.gather()
    assert any("queue is empty" in r.lower() for r in d["next_steps"])
    assert any("sales" in r.lower() for r in d["next_steps"])


# ------------------------------------------------------------ dashboard
@pytest.fixture
def server():
    srv = dashboard.make_server("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _post(url, data, headers=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data, doseq=True).encode(), headers=headers or {})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def test_dashboard_pages(server):
    for path in ("/", "/products", "/report", "/money", "/api/status"):
        code, _ = _get(server + path)
        assert code == 200, path
    assert _get(server + "/product/999")[0] == 404
    assert _get(server + "/files/../../etc/passwd")[0] == 404


def test_dashboard_queue_job(server):
    form = {"theme": "Lavender Garden Bridal Shower", "preset": "Lavender Dream",
            "c1": "#F4F0FA", "c2": "#B39DDB", "c3": "#E6B8D8", "c4": "#4A3B66",
            "types": ["strip_2x6", "overlay_4x6"], "w_strip_2x6": "600", "h_strip_2x6": "1800",
            "w_overlay_4x6": "1200", "h_overlay_4x6": "1800", "variations": "3", "action": "queue"}
    code, _ = _post(server + "/jobs", form)
    assert code == 303
    j = db.one("SELECT * FROM jobs ORDER BY id DESC")
    assert j["theme"] == "Lavender Garden Bridal Shower" and j["palette"] == "Lavender Dream"
    assert db.get_job(j["id"])["sizes"] == {"overlay_4x6": [1200, 1800]}  # only non-default sizes stored
    assert j["status"] == "queued"


def test_dashboard_blocks_bad_input(server):
    code, body = _post(server + "/jobs", {"theme": "Super Mario Party", "types": ["buttons"], "preset": "Pastel Party"})
    assert code == 400 and "mario" in body.lower()
    code, _ = _post(server + "/run", {}, headers={"Origin": "http://evil.example"})
    assert code == 403
    assert db.one("SELECT COUNT(*) n FROM jobs")["n"] == 0


def test_dashboard_status_and_sales(server, small_sizes):
    from studio import pipeline
    jid = db.add_job("Coastal Summer Party", "Ocean Breeze", ["gif_overlay"], 1, small_sizes, seed=1)
    pid = pipeline.build_job(jid, log=lambda *a: None)
    code, body = _get(f"{server}/product/{pid}")
    assert code == 200 and "Coastal Summer Party" in body
    assert _post(f"{server}/product/{pid}/status", {"status": "approved"})[0] == 303
    assert db.get_product(pid)["status"] == "approved"
    assert _post(server + "/sales/import", {"csv": ETSY_CSV})[0] == 303
    assert db.one("SELECT COUNT(*) n FROM sales")["n"] == 3
    assert _post(server + "/costs", {"category": "advertising", "amount": "2.50", "note": "pin promo"})[0] == 303
