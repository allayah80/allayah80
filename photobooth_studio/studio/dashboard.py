"""Local dashboard (Python standard library only).

Run:  python -m studio dashboard   then open http://127.0.0.1:8765
It listens on your own computer only and has no publish/post/purchase actions.
"""
from __future__ import annotations

import html
import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import db, pipeline, report, sales
from .config import PRODUCT_SPECS, PRODUCT_TYPES, load_settings, out_dirs
from .palettes import PRESETS, parse_palette
from .themes import find_blocked

e = html.escape

# ---------------------------------------------------------------- background worker
WORK = {"busy": False, "task": "", "log": []}
_work_lock = threading.Lock()


def _log(msg):
    WORK["log"] = (WORK["log"] + [str(msg)])[-60:]


def run_background(name, fn, *args):
    with _work_lock:
        if WORK["busy"]:
            return False
        WORK.update(busy=True, task=name, log=[])

    def target():
        try:
            fn(*args)
        except Exception as ex:
            _log(f"ERROR: {ex}")
            _log(traceback.format_exc(limit=2))
        finally:
            WORK["busy"] = False
            _log("Finished.")
    threading.Thread(target=target, daemon=True).start()
    return True


# ---------------------------------------------------------------- page chrome
CSS = """
:root{--bg:#f6f4f1;--card:#fff;--ink:#22201e;--muted:#6f6a64;--line:#e5e0d9;--accent:#7a4fd0;--ok:#1f8a4c;--bad:#c0392b;--chip:#efeaf9}
@media (prefers-color-scheme:dark){:root{--bg:#17161a;--card:#222126;--ink:#efedf2;--muted:#a19ca8;--line:#36343c;--accent:#a68af0;--ok:#4cc27f;--bad:#ff6b5b;--chip:#2e2a3a}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
header{display:flex;gap:18px;align-items:center;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:2;flex-wrap:wrap}
header b{font-size:17px}header a{color:var(--muted);text-decoration:none}header a:hover{color:var(--ink)}
main{max-width:1200px;margin:0 auto;padding:24px 16px;overflow-wrap:anywhere}.tw{overflow-x:auto}video{max-width:100%}
h1{font-size:24px;margin:4px 0 16px}h2{font-size:18px;margin:28px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.prod img{width:100%;border-radius:8px;aspect-ratio:4/3;object-fit:cover;background:var(--line)}
.prod a{color:inherit;text-decoration:none}.prod .t{font-weight:600;font-size:14px;margin:8px 0 4px}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;background:var(--chip);font-size:12px;margin-right:4px}
.chip.draft{background:#fff1c9;color:#6b5200}.chip.approved{background:#d6f5e2;color:#145c33}.chip.rejected{background:#fde0dc;color:#7d1d12}.chip.listed{background:#dbe8ff;color:#123d80}
.ok{color:var(--ok)}.bad{color:var(--bad)}.muted{color:var(--muted)}
label{display:block;font-weight:600;font-size:13px;margin:12px 0 4px}
input,select,textarea{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);width:100%}
input[type=color]{padding:2px;height:38px;width:56px}input[type=checkbox]{width:auto}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.row>*{flex:1;min-width:120px}
.types{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px}.types label{min-width:120px;overflow-wrap:normal}
.types div{display:flex;gap:8px;align-items:center;border:1px solid var(--line);border-radius:8px;padding:8px}
.types input[type=number]{width:76px;flex:0 0 76px;padding:6px}
button,.btn{font:inherit;font-weight:600;padding:9px 16px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;text-decoration:none;display:inline-block}
button.ghost,.btn.ghost{background:transparent;color:var(--accent)}button.danger{background:var(--bad);border-color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:12px}
.stats div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}.stats b{font-size:24px;display:block}.stats span{color:var(--muted);font-size:13px}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:13px;max-height:420px;overflow:auto}
.swatches span{display:inline-block;width:22px;height:22px;border-radius:5px;border:1px solid var(--line);margin-right:3px;vertical-align:middle}
#work{position:fixed;right:16px;bottom:16px;max-width:420px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;box-shadow:0 6px 24px #0003;display:none;font-size:13px}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.gallery img{width:100%;border-radius:8px;border:1px solid var(--line)}
@media (max-width:600px){main{padding:16px}header{padding:12px 16px}}
"""

JS = """
async function poll(){try{const r=await fetch('/api/status');const s=await r.json();const w=document.getElementById('work');
if(s.busy||s.log.length){w.style.display='block';w.innerHTML='<b>'+(s.busy?'Working: ':'Last task: ')+s.task+'</b><pre>'+s.log.slice(-8).join('\\n').replace(/</g,'&lt;')+'</pre>'+(s.busy?'':'<a href="">Refresh page</a>');}
if(s.busy)setTimeout(poll,2000);}catch(e){}}
poll();
function pickFile(inp){const f=inp.files[0];if(!f)return;const r=new FileReader();r.onload=()=>{document.getElementById('csvtext').value=r.result};r.readAsText(f);}
function applyPreset(sel){const p=PRESETS[sel.value];if(!p)return;['c1','c2','c3','c4'].forEach((id,i)=>document.getElementById(id).value=p[i]);}
"""


def page(title, body):
    # wide tables scroll inside their own box on small screens
    body = body.replace("<table>", "<div class=tw><table>").replace("</table>", "</table></div>")
    nav = ("<header><b>📸 Photo Booth Studio</b><a href='/'>Dashboard</a><a href='/products'>Inventory</a>"
           "<a href='/report'>Daily report</a><a href='/money'>Sales &amp; costs</a></header>")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(title)} · Photo Booth Studio</title><style>{CSS}</style></head><body>{nav}<main>{body}</main>"
            f"<div id=work></div><script>const PRESETS={json.dumps(PRESETS)};{JS}</script></body></html>")


def file_url(path: Path) -> str:
    base = out_dirs()["base"].resolve()
    try:
        return "/files/" + quote(str(Path(path).resolve().relative_to(base)))
    except ValueError:
        return "#"


def swatches(pals):
    return "".join("<span class=swatches>" + "".join(f"<span style='background:{c}'></span>" for c in p["colors"])
                   + f" {e(p['name'])}</span><br>" for p in pals)


def product_card(p):
    hero = Path(p["bundle_dir"]) / "previews" / "01_hero.jpg"
    img = f"<img loading=lazy src='{file_url(hero)}' alt=''>" if hero.exists() else "<img alt=''>"
    return (f"<div class='card prod'><a href='/product/{p['id']}'>{img}<div class=t>{e(p['title'][:90])}</div></a>"
            f"<span class='chip {p['status']}'>{p['status']}</span><span class=chip>${p['price']:.2f}</span>"
            f"<span class='chip {'ok' if p['valid'] else 'bad'}'>{'valid' if p['valid'] else 'issues'}</span>"
            f"<div class=muted style='font-size:12px;margin-top:6px'>{e(p['sku'])}</div></div>")


# ---------------------------------------------------------------- pages
def home():
    st = load_settings()
    counts = {r["status"]: r["n"] for r in db.rows("SELECT status, COUNT(*) n FROM products GROUP BY status")}
    money = sales.summary(30)
    queue = db.rows("SELECT * FROM jobs WHERE status IN ('queued','running','failed') ORDER BY id DESC LIMIT 15")
    recent = db.rows("SELECT * FROM products ORDER BY updated_at DESC LIMIT 8")
    preset_opts = "".join(f"<option>{e(k)}</option>" for k in PRESETS)
    first = list(PRESETS.values())[0]
    types = "".join(
        f"<div><input type=checkbox name=types value={t} id=t_{t} checked><label for=t_{t} style='margin:0;flex:1'>"
        f"{e(s['label'])}</label><input type=number name=w_{t} value={s['size'][0]} min=50 max=8000 title=width>"
        f"×<input type=number name=h_{t} value={s['size'][1]} min=50 max=8000 title=height></div>"
        for t, s in PRODUCT_SPECS.items())
    qrows = "".join(
        f"<tr><td>#{j['id']}</td><td>{e(j['theme'])}</td><td>{e(j['source'])}</td><td>{e(j['status'])}"
        f"{'<br><span class=bad>' + e(j['error'] or '') + '</span>' if j['status'] == 'failed' else ''}</td>"
        f"<td>{'<form method=post action=/job/' + str(j['id']) + '/delete><button class=ghost>Remove</button></form>' if j['status'] in ('queued', 'failed') else ''}</td></tr>"
        for j in queue) or "<tr><td colspan=5 class=muted>Queue is empty. Autopilot will pick seasonal themes tonight.</td></tr>"
    body = f"""
<div class=stats>
 <div><b>{counts.get('draft', 0)}</b><span>drafts to review</span></div>
 <div><b>{counts.get('approved', 0)}</b><span>approved (ready to list)</span></div>
 <div><b>{counts.get('listed', 0)}</b><span>listed</span></div>
 <div><b>${money['revenue']:.2f}</b><span>revenue, 30 days</span></div>
 <div><b>{report._m(money['profit'])}</b><span>profit, 30 days</span></div>
</div>
<div class=card><h1>New product bundle</h1>
<form method=post action=/jobs>
 <label>Theme</label><input name=theme required placeholder="e.g. Rustic Boho Wedding, Neon Glow 21st Birthday, Winter Wonderland Gala">
 <p class=muted style=margin:4px 0 0>Use original themes only - brand names, characters and franchises are blocked automatically.</p>
 <label>Color palette (background, primary, accent, text)</label>
 <div class=row><select name=preset onchange=applyPreset(this)>{preset_opts}</select>
  <input type=color id=c1 name=c1 value={first[0]}><input type=color id=c2 name=c2 value={first[1]}>
  <input type=color id=c3 name=c3 value={first[2]}><input type=color id=c4 name=c4 value={first[3]}></div>
 <label>Product types &amp; dimensions (pixels)</label><div class=types>{types}</div>
 <div class=row><div><label>Color variations</label><input type=number name=variations value={st['default_variations']} min=1 max=8></div>
  <div><label>Seed (optional, same seed = same layout)</label><input type=number name=seed></div></div>
 <div class=row style="margin-top:16px;flex:none"><button name=action value=queue>Add to overnight queue</button>
  <button class=ghost name=action value=now>Build now</button></div>
</form></div>
<div class=card><div class=row style="justify-content:space-between"><h2 style=margin:0>Queue</h2>
 <form method=post action=/run style=flex:none><button class=ghost>Run overnight workflow now</button></form></div>
 <table><tr><th>Job</th><th>Theme</th><th>Source</th><th>Status</th><th></th></tr>{qrows}</table></div>
<h2>Recently built</h2><div class=grid>{''.join(product_card(p) for p in recent) or '<p class=muted>No products yet.</p>'}</div>
"""
    return page("Dashboard", body)


def products_page(q):
    status = q.get("status", [""])[0]
    where, params = ("WHERE status=?", (status,)) if status else ("", ())
    ps = db.rows(f"SELECT * FROM products {where} ORDER BY id DESC", params)
    tabs = " ".join(f"<a class='btn {'ghost' if s != status else ''}' href='/products?status={s}'>{s or 'all'}</a>"
                    for s in ("", "draft", "approved", "listed", "rejected"))
    export = ("<form method=post action=/export/shopify style='margin:0 0 16px'><button class=ghost>"
              "Export approved products to a Shopify import CSV</button></form>")
    return page("Inventory", f"<h1>Inventory ({len(ps)})</h1><div class=row style='flex:none;gap:6px;margin-bottom:16px'>{tabs}</div>{export}"
                f"<div class=grid>{''.join(product_card(p) for p in ps) or '<p class=muted>Nothing here.</p>'}</div>")


def product_page(pid):
    p = db.get_product(pid)
    if not p:
        return None
    root = Path(p["bundle_dir"])
    prev = sorted((root / "previews").glob("*")) if (root / "previews").exists() else []
    mk = sorted((root / "marketing").glob("*")) if (root / "marketing").exists() else []
    gallery = "".join(f"<a href='{file_url(x)}' target=_blank><img loading=lazy src='{file_url(x)}' alt='{e(x.name)}'></a>"
                      for x in prev if x.suffix in (".jpg", ".png", ".gif"))
    mk_imgs = "".join(f"<a href='{file_url(x)}' target=_blank><img loading=lazy src='{file_url(x)}' alt='{e(x.name)}'></a>"
                      for x in mk if x.suffix == ".png")
    mk_vids = "".join(f"<video src='{file_url(x)}' controls muted loop style='max-width:280px;border-radius:8px'></video>"
                      for x in mk if x.suffix == ".mp4")
    videos = sorted((root / "product").rglob("*.mp4"))
    vid = (f"<h2>Animated welcome screen</h2><video src='{file_url(videos[0])}' autoplay muted loop controls "
           f"style='width:100%;max-width:720px;border-radius:8px'></video>") if videos else ""
    captions = (root / "marketing" / "captions.md")
    cap = f"<h2>Captions &amp; scripts (draft)</h2><pre>{e(captions.read_text())}</pre>" if captions.exists() else ""
    def store_of(z):
        parts = Path(z).parts
        return parts[1] if len(parts) > 2 else "files"
    zips = ""
    for store in dict.fromkeys(store_of(z) for z in p["zip_files"]):
        items = "".join(f"<li><a href='{file_url(root / z)}'>{e(Path(z).name)}</a> "
                        f"({(root / z).stat().st_size / 1e6:.1f} MB)</li>"
                        for z in p["zip_files"] if store_of(z) == store and (root / z).exists())
        zips += f"<h3>{e(store.title())}</h3><ul>{items}</ul>"
    shop_csv = root / "listing" / "shopify_product_import.csv"
    if shop_csv.exists():
        zips += (f"<p><a class='btn ghost' href='{file_url(shop_csv)}'>Shopify import CSV (creates a draft)</a> "
                 f"<span class=muted>Square photos: <code>previews/square/</code></span></p>")
    v = p["validation"] or {}
    errs = "".join(f"<li><code>{e(x['stage'])}</code> {e(x['message'][:400])}</li>" for x in v.get("errors", []))
    lst = root / "listing" / "listing.json"
    meta = json.loads(lst.read_text()) if lst.exists() else {}
    by_store = meta.get("by_store") or {"store": {"fees": meta.get("estimated_fees", 0), "net": meta.get("estimated_net", 0)}}
    fee_txt = "; ".join(f"{k.title()}: fees ${v['fees']:.2f}, net ${v['net']:.2f}" for k, v in by_store.items())
    sh = meta.get("shopify")
    shopify_card = "" if not sh else f"""<div class=card><h2 style=margin-top:0>Shopify fields</h2>
 <p><b>URL handle:</b> {e(sh['handle'])}</p>
 <p><b>SEO title</b> <span class=muted>({len(sh['seo_title'])}/70)</span><br>{e(sh['seo_title'])}</p>
 <p><b>SEO description</b> <span class=muted>({len(sh['seo_description'])}/320)</span><br>{e(sh['seo_description'])}</p>
 <p><b>Type:</b> {e(sh['product_type'])} &nbsp; <b>Tags:</b> {' '.join(f'<span class=chip>{e(t)}</span>' for t in sh['tags'])}</p></div>"""
    actions = "".join(
        f"<button name=status value={s} class='{ {'approved': '', 'rejected': 'danger'}.get(s, 'ghost') }'>{label}</button> "
        for s, label in (("approved", "Approve"), ("rejected", "Reject"), ("listed", "Mark as listed"), ("draft", "Back to draft"))
        if s != p["status"])
    body = f"""
<p><a href=/products>&larr; Inventory</a></p>
<h1>{e(p['title'])}</h1>
<p><span class='chip {p['status']}'>{p['status']}</span><span class=chip>{e(p['sku'])}</span><span class=chip>{e(p['category'] or '')}</span>
<span class='chip'>{'<span class=ok>all files valid</span>' if p['valid'] else '<span class=bad>validation issues</span>'}</span></p>
<div class=card><form method=post action=/product/{pid}/status class=row style=flex:none;gap:8px>
 {actions}<input name=note placeholder="optional note" style=max-width:260px></form>
 <form method=post action=/product/{pid}/variations class=row style="flex:none;gap:8px;margin-top:10px">
 <input type=number name=extra value=2 min=1 max=6 style=max-width:90px><button class=ghost>Add more color variations</button></form>
 <p class=muted style=margin-bottom:0>Approving does <b>not</b> publish anything. Upload the files to your shop yourself, then click "Mark as listed".</p></div>
<h2>Listing previews</h2><div class=gallery>{gallery}</div>
{vid}
<div class=card><h2 style=margin-top:0>Listing copy</h2>
 <p><b>Suggested price:</b> ${p['price']:.2f} <span class=muted>({e(fee_txt)}; {e(meta.get('rationale', ''))})</span></p>
 <p><b>Etsy tags:</b> {' '.join(f'<span class=chip>{e(t)}</span>' for t in p['tags'])}</p>
 <pre>{e(p['description'])}</pre>
 <p><b>Colors:</b><br>{swatches(p['palettes'])}</p></div>
{shopify_card}
<div class=card><h2 style=margin-top:0>Download files (for you to upload)</h2>{zips}
 <p class=muted>Folder: {e(str(root))}</p>
 <h3>Validation</h3><p>{v.get('files_ok', 0)}/{v.get('files_checked', 0)} files passed.</p><ul>{errs or '<li class=ok>No issues.</li>'}</ul></div>
<h2>Marketing drafts (not posted)</h2><div class=gallery>{mk_imgs}</div><div class=row style=margin-top:12px>{mk_vids}</div>
{cap}
"""
    return page(p["sku"], body)


def money_page():
    costs = db.rows("SELECT * FROM costs ORDER BY id DESC LIMIT 50")
    sales_rows = db.rows("SELECT * FROM sales ORDER BY date DESC, id DESC LIMIT 50")
    s30, sall = sales.summary(30), sales.summary(None)
    crow = "".join(f"<tr><td>{e(c['date'])}</td><td>{e(c['category'])}</td><td>${c['amount']:.4f}</td><td>{e(c['note'] or '')}</td></tr>" for c in costs)
    srow = "".join(f"<tr><td>{e(s['date'])}</td><td>{e(s['sku'] or '')}</td><td>{e((s['title'] or '')[:60])}</td><td>{s['quantity']}</td>"
                   f"<td>${s['revenue']:.2f}</td><td>${s['fees']:.2f}</td></tr>" for s in sales_rows)
    body = f"""
<h1>Sales &amp; costs</h1>
<div class=stats><div><b>${s30['revenue']:.2f}</b><span>revenue 30d</span></div><div><b>${s30['costs']:.2f}</b><span>costs 30d</span></div>
<div><b>{report._m(s30['profit'])}</b><span>profit 30d</span></div><div><b>{report._m(sall['profit'])}</b><span>profit all time</span></div></div>
<div class=card><h2 style=margin-top:0>Import sales CSV</h2>
<p class=muted>Download your orders CSV and load it here. Duplicates are skipped.<br>
<b>Etsy:</b> Shop Manager → Settings → Options → Download Data → Sold Order Items.<br>
<b>Shopify:</b> Orders → Export → All orders, "CSV for Excel, Numbers, or other spreadsheet programs" (detected automatically; card fees are estimated from your settings).</p>
<form method=post action=/sales/import><input type=file accept=.csv onchange=pickFile(this)>
<textarea id=csvtext name=csv rows=5 placeholder="...or paste CSV text"></textarea><p><button>Import</button></p></form></div>
<div class=card><h2 style=margin-top:0>Record a cost</h2><form method=post action=/costs class=row>
<select name=category><option>listing fees</option><option>advertising</option><option>software</option><option>assets</option><option>other</option></select>
<input name=amount type=number step=0.01 min=0 placeholder=Amount required><input name=note placeholder=Note><button style=flex:none>Add</button></form>
<p class=muted>Compute (electricity) cost for each render is recorded automatically.</p></div>
<h2>Recent sales</h2><table><tr><th>Date</th><th>SKU</th><th>Item</th><th>Qty</th><th>Revenue</th><th>Fees</th></tr>{srow or '<tr><td colspan=6 class=muted>No sales imported yet.</td></tr>'}</table>
<h2>Recent costs</h2><table><tr><th>Date</th><th>Category</th><th>Amount</th><th>Note</th></tr>{crow}</table>
"""
    return page("Sales & costs", body)


def report_page():
    d = report.gather()
    report.daily_report()
    return page("Daily report", report.to_html(d))


# ---------------------------------------------------------------- actions
def create_job(form) -> tuple[int | None, str]:
    g = lambda k, d="": form.get(k, [d])[0].strip()
    theme = g("theme")
    if not theme:
        return None, "Please enter a theme."
    hits = find_blocked(theme)
    if hits:
        return None, f"Theme blocked: contains protected brand/character terms ({', '.join(hits)})."
    types = [t for t in form.get("types", []) if t in PRODUCT_TYPES]
    if not types:
        return None, "Pick at least one product type."
    colors = [g(k) for k in ("c1", "c2", "c3", "c4") if g(k)]
    palette = ",".join(colors) if colors else g("preset", "Blush & Gold")
    if g("preset") in PRESETS and [c.upper() for c in colors] == [c.upper() for c in PRESETS[g("preset")]]:
        palette = g("preset")
    try:
        parse_palette(palette)
    except ValueError as ex:
        return None, str(ex)
    sizes = {}
    for t in types:
        try:
            w, h = int(g(f"w_{t}")), int(g(f"h_{t}"))
            if (w, h) != tuple(PRODUCT_SPECS[t]["size"]) and 50 <= w <= 8000 and 50 <= h <= 8000:
                sizes[t] = [w, h]
        except ValueError:
            pass
    variations = max(1, min(8, int(g("variations", "4") or 4)))
    seed = int(g("seed")) if g("seed").isdigit() else None
    return db.add_job(theme, palette, types, variations, sizes, seed, source="dashboard"), ""


class Handler(BaseHTTPRequestHandler):
    server_version = "PhotoBoothStudio"

    def log_message(self, fmt, *args):
        pass

    def send(self, body, status=200, ctype="text/html; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def error_page(self, msg, status=400):
        self.send(page("Error", f"<div class=card><h1>Something needs attention</h1><p>{e(msg)}</p>"
                                f"<p><a href='javascript:history.back()'>Go back</a></p></div>"), status)

    def do_GET(self):
        try:
            u = urlparse(self.path)
            parts = [x for x in u.path.split("/") if x]
            if not parts:
                return self.send(home())
            if parts[0] == "products":
                return self.send(products_page(parse_qs(u.query)))
            if parts[0] == "product" and len(parts) == 2 and parts[1].isdigit():
                html_ = product_page(int(parts[1]))
                return self.send(html_) if html_ else self.error_page("Product not found", 404)
            if parts[0] == "report":
                return self.send(report_page())
            if parts[0] == "money":
                return self.send(money_page())
            if parts[0] == "api" and parts[1:] == ["status"]:
                return self.send(json.dumps(WORK), ctype="application/json")
            if parts[0] == "files":
                return self.serve_file(unquote(u.path[len("/files/"):]))
            self.error_page("Not found", 404)
        except Exception as ex:
            self.error_page(f"{ex}", 500)

    def serve_file(self, rel):
        base = out_dirs()["base"].resolve()
        p = (base / rel).resolve()
        if base not in p.parents or not p.is_file():  # blocks ../ path traversal
            return self.error_page("File not found", 404)
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        self.send(p.read_bytes(), ctype=ctype)

    def do_POST(self):
        try:
            # Only accept form posts that come from this dashboard.
            origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
            host = self.headers.get("Host", "")
            if origin and urlparse(origin).netloc != host:
                return self.error_page("Cross-site request blocked.", 403)
            n = int(self.headers.get("Content-Length", 0))
            if n > 20_000_000:
                return self.error_page("Request too large", 413)
            form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True)
            parts = [x for x in urlparse(self.path).path.split("/") if x]
            if parts == ["jobs"]:
                jid, msg = create_job(form)
                if not jid:
                    return self.error_page(msg)
                if form.get("action", ["queue"])[0] == "now":
                    run_background(f"Build job #{jid}", lambda: pipeline.build_job(jid, None, _log))
                return self.redirect("/")
            if parts == ["run"]:
                from . import scheduler
                run_background("Overnight workflow", lambda: scheduler.run_overnight(log=_log))
                return self.redirect("/")
            if len(parts) == 3 and parts[0] == "job" and parts[2] == "delete":
                db.execute("DELETE FROM jobs WHERE id=? AND status IN ('queued','failed')", (int(parts[1]),))
                return self.redirect("/")
            if len(parts) == 3 and parts[0] == "product":
                pid = int(parts[1])
                if parts[2] == "status":
                    db.set_product_status(pid, form["status"][0], (form.get("note", [""])[0] or None))
                elif parts[2] == "variations":
                    extra = max(1, min(6, int(form.get("extra", ["2"])[0])))
                    run_background(f"Add {extra} variations to product #{pid}",
                                   lambda: pipeline.add_variations(pid, extra, None, _log))
                return self.redirect(f"/product/{pid}")
            if parts == ["sales", "import"]:
                added, skipped = sales.import_text(form.get("csv", [""])[0])
                _log(f"Sales import: {added} added, {skipped} skipped")
                return self.redirect("/money")
            if parts == ["export", "shopify"]:
                from . import stores
                path = stores.export_products(db.rows("SELECT * FROM products WHERE status='approved' ORDER BY id"))
                if not path:
                    return self.error_page("No approved products with Shopify listing data yet. Approve a product "
                                           "built with Shopify mode on, then try again.")
                return self.send(page("Shopify export", f"<div class=card><h1>Shopify import file ready</h1>"
                                      f"<p><a class=btn href='{file_url(path)}'>Download {e(path.name)}</a></p>"
                                      "<p>In Shopify admin: <b>Products → Import</b>, choose this file. Products are "
                                      "created as <b>drafts</b> (not published, no shipping). Then add the square "
                                      "photos and attach each ZIP in your digital downloads app.</p></div>"))
            if parts == ["costs"]:
                db.add_cost(form["category"][0], float(form["amount"][0]), form.get("note", [""])[0])
                return self.redirect("/money")
            self.error_page("Unknown action", 404)
        except Exception as ex:
            self.error_page(str(ex), 500)


def make_server(host="127.0.0.1", port=8765) -> ThreadingHTTPServer:
    out_dirs()
    return ThreadingHTTPServer((host, port), Handler)


def serve(host="127.0.0.1", port=8765):
    srv = make_server(host, port)
    print(f"Photo Booth Studio dashboard: http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
