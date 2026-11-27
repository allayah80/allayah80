"""Command line entry point:  python -m studio <command> ..."""
from __future__ import annotations

import argparse
import json
import sys

from . import db, pipeline
from .config import PRODUCT_TYPES, load_settings, out_dirs
from .palettes import PRESETS


def _sizes(args_sizes):
    sizes = {}
    for s in args_sizes or []:
        ptype, wh = s.split("=")
        w, h = wh.lower().split("x")
        sizes[ptype] = [int(w), int(h)]
    return sizes


def cmd_build(a):
    types = a.types.split(",") if a.types else PRODUCT_TYPES
    jid = db.add_job(a.theme, a.palette, types, a.variations or load_settings()["default_variations"],
                     _sizes(a.size), a.seed, source="cli")
    if a.queue:
        print(f"Queued job {jid} for the overnight run.")
        return 0
    run = db.start_run("manual")
    pid = pipeline.build_job(jid, run)
    p = db.get_product(pid) if pid else None
    db.finish_run(run, int(bool(pid)), 0 if p and p["valid"] else 1, 0)
    if not p:
        return 1
    print(f"\nDraft ready: {p['bundle_dir']}\nTitle: {p['title']}\nPrice: ${p['price']:.2f}  Valid: {bool(p['valid'])}")
    return 0 if p["valid"] else 2


def cmd_list(a):
    for p in db.rows("SELECT id, sku, status, valid, price, title FROM products ORDER BY id DESC LIMIT ?", (a.limit,)):
        print(f"#{p['id']:<4} {p['sku']:<16} {p['status']:<9} {'OK ' if p['valid'] else 'ERR'} "
              f"${p['price']:<6} {p['title'][:70]}")


def cmd_status(a):
    db.set_product_status(a.id, a.status, a.note)
    print(f"Product {a.id} -> {a.status}")


def cmd_variations(a):
    pid = pipeline.add_variations(a.id, a.extra)
    print("Rebuilt product", pid)


def cmd_presets(a):
    for k, v in PRESETS.items():
        print(f"{k:<18} {' '.join(v)}")


def cmd_overnight(a):
    from . import scheduler
    return scheduler.run_overnight(max_jobs=a.max, autopilot=None if a.autopilot is None else a.autopilot == "on")


def cmd_report(a):
    from . import report
    path = report.daily_report(a.date)
    print(path)


def cmd_dashboard(a):
    from .dashboard import serve
    serve(a.host, a.port)


def cmd_import_sales(a):
    from . import sales
    added, skipped = sales.import_csv(a.csv, a.source)
    print(f"Imported {added} sale rows ({skipped} duplicates/invalid skipped).")


def cmd_shopify_csv(a):
    from . import stores
    if a.ids:
        prods = [db.get_product(int(i)) for i in a.ids.split(",")]
    else:
        prods = db.rows("SELECT * FROM products WHERE status=? ORDER BY id", (a.status,))
    path = stores.export_products([p for p in prods if p])
    print(path or "No matching products with Shopify listing data.")


def cmd_cost(a):
    db.add_cost(a.category, a.amount, a.note or "")
    print("Cost recorded.")


def main(argv=None):
    out_dirs()
    ap = argparse.ArgumentParser(prog="studio", description="Photo Booth Studio")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a draft bundle now (or --queue it for tonight)")
    b.add_argument("--theme", required=True)
    b.add_argument("--palette", required=True, help='preset name or hex list, e.g. "#FBEFEF,#E8A5B4,#C9A227"')
    b.add_argument("--types", help=f"comma list from: {','.join(PRODUCT_TYPES)} (default: all)")
    b.add_argument("--variations", type=int)
    b.add_argument("--size", action="append", help="override size, e.g. --size welcome_screen=1080x1920")
    b.add_argument("--seed", type=int)
    b.add_argument("--queue", action="store_true")
    b.set_defaults(fn=cmd_build)

    l = sub.add_parser("list", help="list products")
    l.add_argument("--limit", type=int, default=30)
    l.set_defaults(fn=cmd_list)

    s = sub.add_parser("status", help="set product status (approve/reject/listed)")
    s.add_argument("id", type=int)
    s.add_argument("status", choices=["draft", "approved", "rejected", "listed", "retired"])
    s.add_argument("--note")
    s.set_defaults(fn=cmd_status)

    v = sub.add_parser("variations", help="add more color variations to a product")
    v.add_argument("id", type=int)
    v.add_argument("--extra", type=int, default=2)
    v.set_defaults(fn=cmd_variations)

    sub.add_parser("presets", help="show palette presets").set_defaults(fn=cmd_presets)

    o = sub.add_parser("overnight", help="process the queue (used by the scheduler)")
    o.add_argument("--max", type=int)
    o.add_argument("--autopilot", choices=["on", "off"])
    o.set_defaults(fn=cmd_overnight)

    r = sub.add_parser("report", help="write the daily report")
    r.add_argument("--date")
    r.set_defaults(fn=cmd_report)

    d = sub.add_parser("dashboard", help="start the local dashboard")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8765)
    d.set_defaults(fn=cmd_dashboard)

    i = sub.add_parser("import-sales", help="import a sales CSV export")
    i.add_argument("csv")
    i.add_argument("--source", default="etsy")
    i.set_defaults(fn=cmd_import_sales)

    x = sub.add_parser("shopify-csv", help="write a Shopify product import CSV (drafts)")
    x.add_argument("--status", default="approved")
    x.add_argument("--ids", help="comma-separated product ids instead of --status")
    x.set_defaults(fn=cmd_shopify_csv)

    c = sub.add_parser("cost", help="record a manual cost")
    c.add_argument("category")
    c.add_argument("amount", type=float)
    c.add_argument("--note")
    c.set_defaults(fn=cmd_cost)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
