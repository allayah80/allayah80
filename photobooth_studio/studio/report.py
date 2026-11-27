"""Daily report: completed products, errors, money and recommended next steps."""
from __future__ import annotations

import html
from datetime import date, datetime
from pathlib import Path

from . import db, sales
from .config import load_settings, out_dirs


def _m(v) -> str:
    v = round(float(v or 0), 2) or 0.0  # avoid "-0.00"
    return f"${v:.2f}"


def gather(day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    products = db.rows("SELECT id, sku, title, price, status, valid, zip_files, bundle_dir, render_seconds, theme "
                       "FROM products WHERE substr(updated_at,1,10)=? ORDER BY id", (day,))
    errors = db.rows("SELECT stage, message, job_id, created_at FROM errors WHERE substr(created_at,1,10)=? ORDER BY id",
                     (day,))
    failed_jobs = db.rows("SELECT id, theme, error FROM jobs WHERE status='failed' AND substr(finished_at,1,10)=?", (day,))
    runs = db.rows("SELECT * FROM runs WHERE substr(started_at,1,10)=? ORDER BY id", (day,))
    counts = {r["status"]: r["n"] for r in db.rows("SELECT status, COUNT(*) n FROM products GROUP BY status")}
    queued = db.one("SELECT COUNT(*) n FROM jobs WHERE status='queued'")["n"]
    last_sale = db.one("SELECT MAX(date) d FROM sales")["d"]
    from .scheduler import upcoming_seasons
    st = load_settings()
    data = {
        "day": day, "products": products, "errors": errors, "failed_jobs": failed_jobs, "runs": runs,
        "counts": counts, "queued": queued, "last_sale": last_sale,
        "money_today": sales.summary(1), "money_30": sales.summary(30), "money_all": sales.summary(None),
        "top": sales.top_sellers(), "seasons": upcoming_seasons(weeks=st.get("autopilot_lead_weeks", 8) + 4),
    }
    data["next_steps"] = recommendations(data)
    return data


def recommendations(d: dict) -> list[str]:
    rec = []
    drafts = d["counts"].get("draft", 0)
    approved = d["counts"].get("approved", 0)
    if drafts:
        rec.append(f"Review {drafts} draft bundle(s) in the dashboard: approve or reject each one.")
    if approved:
        rec.append(f"{approved} approved product(s) are ready to list. Upload the ZIP(s), previews and listing copy "
                   "to your shop yourself, then mark them 'listed'.")
    bad = [p for p in d["products"] if not p["valid"]]
    if bad:
        rec.append(f"{len(bad)} product(s) built today have validation issues - open them and check 'Validation' "
                   "before approving.")
    if d["failed_jobs"]:
        rec.append(f"{len(d['failed_jobs'])} job(s) failed (see Errors). Fix the theme/palette and queue again.")
    if not d["queued"]:
        rec.append("The queue is empty. Add themes in the dashboard (autopilot will use seasonal ideas otherwise).")
    for s in d["seasons"][:2]:
        made = db.one("SELECT 1 x FROM jobs WHERE lower(theme)=lower(?)", (s["theme"],))
        if not made:
            rec.append(f"Seasonal opportunity: '{s['theme']}' (event in {s['days_away']} days). Queue it soon - "
                       "listings need a few weeks to get found.")
    if not d["last_sale"]:
        rec.append("No sales data yet. After your first listings go live, import your marketplace sales CSV weekly.")
    elif (date.today() - date.fromisoformat(d["last_sale"][:10])).days > 7:
        rec.append("Sales data is more than a week old - import a fresh sales CSV to keep pricing advice current.")
    if d["top"]:
        rec.append(f"Best seller so far: '{(d['top'][0]['title'] or d['top'][0]['item'])[:60]}'. "
                   "Make more color variations or similar themes of it.")
    return rec


def to_markdown(d: dict) -> str:
    L = [f"# Daily Report - {d['day']}", "", f"_Generated {datetime.now():%Y-%m-%d %H:%M}_", "",
         "## Summary",
         f"- Products built/updated today: **{len(d['products'])}**",
         f"- Errors logged today: **{len(d['errors'])}**",
         f"- Inventory: " + ", ".join(f"{k}: {v}" for k, v in sorted(d["counts"].items())) if d["counts"] else "- Inventory: empty",
         f"- Jobs waiting in queue: {d['queued']}", "",
         "## Completed products"]
    if d["products"]:
        L += ["| SKU | Title | Price | Status | Valid | Build time |", "|---|---|---|---|---|---|"]
        for p in d["products"]:
            L.append(f"| {p['sku']} | {p['title'][:70].replace('|', '/')} | ${p['price']:.2f} | {p['status']} | "
                     f"{'yes' if p['valid'] else 'NO'} | {p['render_seconds']:.0f}s |")
    else:
        L.append("_None today._")
    L += ["", "## Errors"]
    L += [f"- `{e['stage']}` (job {e['job_id']}): {e['message'][:300]}" for e in d["errors"]] or ["_No errors._ "]
    mt, m30, ma = d["money_today"], d["money_30"], d["money_all"]
    L += ["", "## Money", "| Period | Orders | Revenue | Fees | Costs | Profit |", "|---|---|---|---|---|---|"]
    for name, m in (("Today", mt), ("Last 30 days", m30), ("All time", ma)):
        L.append(f"| {name} | {m['orders']} | {_m(m['revenue'])} | {_m(m['fees'])} | {_m(m['costs'])} | {_m(m['profit'])} |")
    if d["top"]:
        L += ["", "### Top sellers"] + [f"- {t['title'] or t['item']}: {t['units']} sold, ${t['revenue']:.2f}" for t in d["top"]]
    L += ["", "## Upcoming seasons"]
    L += [f"- {s['theme']} - event {s['event_date']} ({s['days_away']} days)" for s in d["seasons"]] or ["_None in window._"]
    L += ["", "## Recommended next steps"] + [f"{i}. {r}" for i, r in enumerate(d["next_steps"], 1)]
    L += ["", "---", "Nothing was published, posted, purchased or sent. All products are drafts awaiting your review."]
    return "\n".join(L)


def to_html(d: dict) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(p['sku'])}</td><td><a href='/product/{p['id']}'>{e(p['title'][:80])}</a></td>"
        f"<td>${p['price']:.2f}</td><td>{e(p['status'])}</td><td class='{'ok' if p['valid'] else 'bad'}'>"
        f"{'valid' if p['valid'] else 'issues'}</td></tr>" for p in d["products"]) or "<tr><td colspan=5>None today.</td></tr>"
    errs = "".join(f"<li><code>{e(x['stage'])}</code> {e(x['message'][:300])}</li>" for x in d["errors"]) or "<li>No errors.</li>"
    money = "".join(
        f"<tr><td>{n}</td><td>{m['orders']}</td><td>{_m(m['revenue'])}</td><td>{_m(m['fees'])}</td>"
        f"<td>{_m(m['costs'])}</td><td><b>{_m(m['profit'])}</b></td></tr>"
        for n, m in (("Today", d["money_today"]), ("Last 30 days", d["money_30"]), ("All time", d["money_all"])))
    seasons = "".join(f"<li>{e(s['theme'])} &middot; {s['event_date']} ({s['days_away']} days)</li>" for s in d["seasons"])
    steps = "".join(f"<li>{e(s)}</li>" for s in d["next_steps"])
    return f"""
<h1>Daily report &middot; {d['day']}</h1>
<div class="stats">
  <div><b>{len(d['products'])}</b><span>built today</span></div>
  <div><b>{len(d['errors'])}</b><span>errors today</span></div>
  <div><b>{d['counts'].get('draft', 0)}</b><span>drafts to review</span></div>
  <div><b>{d['queued']}</b><span>queued</span></div>
</div>
<h2>Recommended next steps</h2><ol>{steps}</ol>
<h2>Completed products</h2><table><tr><th>SKU</th><th>Title</th><th>Price</th><th>Status</th><th>Files</th></tr>{rows}</table>
<h2>Errors</h2><ul>{errs}</ul>
<h2>Money</h2><table><tr><th>Period</th><th>Orders</th><th>Revenue</th><th>Fees</th><th>Costs</th><th>Profit</th></tr>{money}</table>
<h2>Upcoming seasons</h2><ul>{seasons or '<li>None in window.</li>'}</ul>
<p class="muted">Nothing was published, posted, purchased or sent.</p>"""


def daily_report(day: str | None = None) -> Path:
    d = gather(day)
    path = out_dirs()["reports"] / f"{d['day']}.md"
    path.write_text(to_markdown(d), encoding="utf-8")
    return path
