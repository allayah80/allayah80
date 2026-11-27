"""SQLite inventory: jobs, products, files, runs, errors, costs and sales."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import out_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT NOT NULL,
    palette TEXT NOT NULL,
    product_types TEXT NOT NULL,      -- JSON list
    sizes TEXT NOT NULL DEFAULT '{}', -- JSON {ptype: [w, h]}
    variations INTEGER NOT NULL DEFAULT 4,
    seed INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'dashboard',  -- dashboard | cli | autopilot
    status TEXT NOT NULL DEFAULT 'queued',     -- queued | running | done | failed
    created_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    sku TEXT UNIQUE NOT NULL,
    theme TEXT NOT NULL,
    category TEXT,
    title TEXT,
    description TEXT,
    tags TEXT,                 -- JSON list
    price REAL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft | approved | rejected | listed | retired
    bundle_dir TEXT,
    zip_files TEXT,            -- JSON list
    palettes TEXT,             -- JSON list
    valid INTEGER DEFAULT 0,
    validation TEXT,           -- JSON report
    render_seconds REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    kind TEXT, variation TEXT, path TEXT, width INTEGER, height INTEGER, bytes INTEGER,
    ok INTEGER, issues TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT, started_at TEXT, finished_at TEXT,
    products_made INTEGER DEFAULT 0, errors INTEGER DEFAULT 0, cpu_seconds REAL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, job_id INTEGER, product_id INTEGER, stage TEXT, message TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, category TEXT, amount REAL, note TEXT, product_id INTEGER, auto INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, order_id TEXT, sku TEXT, title TEXT, quantity INTEGER DEFAULT 1,
    revenue REAL DEFAULT 0, fees REAL DEFAULT 0, source TEXT,
    UNIQUE(order_id, sku, title)
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect():
    con = sqlite3.connect(out_dirs()["db"], timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def rows(sql, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


def execute(sql, params=()) -> int:
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


# ---------------------------------------------------------------- jobs
def add_job(theme, palette, product_types, variations=4, sizes=None, seed=None, source="dashboard") -> int:
    import random
    seed = seed if seed is not None else random.randint(1, 10_000_000)
    return execute(
        "INSERT INTO jobs(theme, palette, product_types, sizes, variations, seed, source, status, created_at)"
        " VALUES (?,?,?,?,?,?,?, 'queued', ?)",
        (theme, palette if isinstance(palette, str) else json.dumps(palette), json.dumps(product_types),
         json.dumps(sizes or {}), int(variations), int(seed), source, now()))


def get_job(job_id):
    j = one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if j:
        j["product_types"] = json.loads(j["product_types"])
        j["sizes"] = json.loads(j["sizes"] or "{}")
    return j


def set_job_status(job_id, status, error=None):
    execute("UPDATE jobs SET status=?, error=?, finished_at=? WHERE id=?",
            (status, error, now() if status in ("done", "failed") else None, job_id))


# ---------------------------------------------------------------- products
def upsert_product(p: dict) -> int:
    existing = one("SELECT id FROM products WHERE sku=?", (p["sku"],))
    cols = ["job_id", "sku", "theme", "category", "title", "description", "tags", "price", "status",
            "bundle_dir", "zip_files", "palettes", "valid", "validation", "render_seconds"]
    vals = [json.dumps(p[c]) if isinstance(p.get(c), (list, dict)) else p.get(c) for c in cols]
    if existing:
        sets = ", ".join(f"{c}=?" for c in cols)
        execute(f"UPDATE products SET {sets}, updated_at=? WHERE id=?", (*vals, now(), existing["id"]))
        return existing["id"]
    return execute(
        f"INSERT INTO products({', '.join(cols)}, created_at, updated_at) VALUES ({', '.join('?' * len(cols))}, ?, ?)",
        (*vals, now(), now()))


def get_product(pid):
    p = one("SELECT * FROM products WHERE id=?", (pid,))
    if p:
        for k in ("tags", "zip_files", "palettes", "validation"):
            p[k] = json.loads(p[k]) if p.get(k) else ([] if k != "validation" else {})
    return p


def set_product_status(pid, status, notes=None):
    assert status in ("draft", "approved", "rejected", "listed", "retired")
    execute("UPDATE products SET status=?, notes=COALESCE(?, notes), updated_at=? WHERE id=?",
            (status, notes, now(), pid))


def replace_files(pid, files: list[dict]):
    with connect() as c:
        c.execute("DELETE FROM files WHERE product_id=?", (pid,))
        c.executemany(
            "INSERT INTO files(product_id, kind, variation, path, width, height, bytes, ok, issues) VALUES (?,?,?,?,?,?,?,?,?)",
            [(pid, f.get("kind"), f.get("variation"), f.get("path"), f.get("width"), f.get("height"),
              f.get("bytes"), int(bool(f.get("ok"))), json.dumps(f.get("issues", []))) for f in files])


# ---------------------------------------------------------------- runs/errors
def start_run(kind) -> int:
    return execute("INSERT INTO runs(kind, started_at) VALUES (?, ?)", (kind, now()))


def finish_run(run_id, products_made, errors, cpu_seconds, notes=""):
    execute("UPDATE runs SET finished_at=?, products_made=?, errors=?, cpu_seconds=?, notes=? WHERE id=?",
            (now(), products_made, errors, cpu_seconds, notes, run_id))


def log_error(stage, message, run_id=None, job_id=None, product_id=None):
    execute("INSERT INTO errors(run_id, job_id, product_id, stage, message, created_at) VALUES (?,?,?,?,?,?)",
            (run_id, job_id, product_id, stage, str(message)[:2000], now()))


# ---------------------------------------------------------------- money
def add_cost(category, amount, note="", product_id=None, date=None, auto=False):
    return execute("INSERT INTO costs(date, category, amount, note, product_id, auto) VALUES (?,?,?,?,?,?)",
                   (date or now()[:10], category, float(amount), note, product_id, int(auto)))


def add_sale(date, order_id, sku, title, quantity, revenue, fees=0.0, source="manual") -> bool:
    try:
        execute("INSERT INTO sales(date, order_id, sku, title, quantity, revenue, fees, source) VALUES (?,?,?,?,?,?,?,?)",
                (date, order_id, sku, title, int(quantity or 1), float(revenue or 0), float(fees or 0), source))
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate import
