"""Builds one draft product bundle from a job. Never publishes anything."""
from __future__ import annotations

import json
import random
import re
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import db, listing, packager, render, themes, validate
from .config import PRODUCT_SPECS, load_settings, out_dirs, spec
from .palettes import parse_palette, variations


class BuildError(Exception):
    pass


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def make_sku(job: dict) -> str:
    """Stable SKU: job creation date + job id (rebuilds keep the same SKU)."""
    d = (job.get("created_at") or datetime.now().isoformat())[2:10].replace("-", "")
    return f"PB{d}-{job['id']:04d}"


def _rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root))


class Builder:
    def __init__(self, job: dict, run_id=None, log=print):
        self.job = job
        self.run_id = run_id
        self.log = log
        self.settings = load_settings()
        self.errors: list[dict] = []
        self.files: list[dict] = []

    # ----------------------------------------------------------- helpers
    def err(self, stage, msg, product_id=None):
        self.errors.append({"stage": stage, "message": msg})
        db.log_error(stage, msg, self.run_id, self.job["id"], product_id)
        self.log(f"  ! [{stage}] {msg}")

    def record(self, kind, variation, path: Path, result: dict):
        self.files.append({"kind": kind, "variation": variation, "path": _rel(path, self.root),
                           "width": result.get("width"), "height": result.get("height"),
                           "bytes": result.get("bytes"), "ok": result["ok"], "issues": result["issues"]})
        if not result["ok"]:
            self.err("validate", f"{_rel(path, self.root)}: {'; '.join(result['issues'])}")

    def size_for(self, ptype):
        s = self.job["sizes"].get(ptype)
        return tuple(s) if s else None

    # ----------------------------------------------------------- stages
    def prepare(self):
        job = self.job
        hits = themes.find_blocked(job["theme"])
        if hits:
            raise BuildError(f"Theme contains protected brand/character terms ({', '.join(hits)}). "
                             "Use an original theme instead.")
        unknown = [t for t in job["product_types"] if t not in PRODUCT_SPECS]
        if unknown:
            raise BuildError(f"Unknown product types: {unknown}")
        self.profile = themes.resolve(job["theme"])
        base = parse_palette(job["palette"])
        self.palettes = variations(base, max(1, int(job["variations"])))
        rng = random.Random(job["seed"])
        self.design = render.Design(
            theme=job["theme"], profile=self.profile, seed=job["seed"],
            headline=rng.choice(self.profile["headlines"]), placeholder=self.profile["placeholder"],
            sizes={k: tuple(v) for k, v in job["sizes"].items()})
        self.sku = make_sku(job)
        self.root = out_dirs()["bundles"] / self.sku
        if self.root.exists():
            shutil.rmtree(self.root)
        self.product_dir = self.root / "product" / f"{self.sku}_{slugify(job['theme'])[:40]}"
        for d in ("previews", "marketing", "listing", "dist"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def render_static(self):
        """Render all PNG products for every color variation."""
        for pal in self.palettes:
            for ptype in self.job["product_types"]:
                if ptype == "welcome_video":
                    continue
                sp = spec(ptype, self.size_for(ptype))
                folder = self.product_dir / sp["folder"] / pal.slug
                try:
                    if ptype == "buttons":
                        for label in sp["labels"]:
                            img = render.button(self.design, pal, label, sp["size"])
                            path = render.save_png(img, folder / f"button_{label.lower()}_{pal.slug}.png")
                            self.record(ptype, pal.name, path, validate.check_image(
                                path, sp["size"], transparent=True, dpi=sp["dpi"]))
                        continue
                    fn = render.RENDERERS[ptype]
                    for with_text in (True, False):
                        img = fn(self.design, pal, with_text=with_text, size=sp["size"])
                        suffix = "text" if with_text else "blank"
                        path = render.save_png(img, folder / f"{ptype}_{pal.slug}_{suffix}.png")
                        self.record(ptype, pal.name, path, validate.check_image(
                            path, sp["size"], transparent=sp["transparent"], dpi=sp["dpi"],
                            windows=img.info.get("windows")))
                        if ptype == "strip_2x6" and with_text:
                            sheet = render.strip_double(img)
                            spath = render.save_png(sheet, folder / f"strip_2x6_{pal.slug}_4x6-print-sheet.png")
                            self.record(ptype, pal.name, spath, validate.check_image(
                                spath, (sp["size"][0] * 2, sp["size"][1]), transparent=True, dpi=300,
                                windows=sheet.info.get("windows")))
                except Exception as e:
                    self.err(f"render:{ptype}", f"{pal.name}: {e}\n{traceback.format_exc(limit=3)}")

    def render_video(self):
        if "welcome_video" not in self.job["product_types"]:
            return
        try:
            from . import animate
        except ImportError:
            self.err("render:welcome_video", "animation module not installed")
            return
        sp = spec("welcome_video", self.size_for("welcome_video"))
        for pal in self.palettes:
            path = self.product_dir / sp["folder"] / pal.slug / f"welcome_loop_{pal.slug}.mp4"
            try:
                animate.welcome_video(self.design, pal, path, sp["size"],
                                      seconds=self.settings["video_seconds"], fps=self.settings["video_fps"])
                self.record("welcome_video", pal.name, path, validate.check_video(path, sp["size"]))
            except Exception as e:
                self.err("render:welcome_video", f"{pal.name}: {e}")

    def make_listing(self):
        sizes = {t: spec(t, self.size_for(t))["size"] for t in self.job["product_types"]}
        self.listing = listing.build_listing(self.sku, self.job["theme"], self.profile,
                                             self.job["product_types"], self.palettes, sizes)
        self.listing.update(listing.price_for(self.job["product_types"], len(self.palettes),
                                              self.profile["category"]))
        for issue in validate.check_listing(self.listing):
            self.err("listing", issue)
        (self.root / "listing" / "listing.json").write_text(json.dumps(self.listing, indent=2), encoding="utf-8")
        md = [f"# {self.listing['title']}", "",
              f"**Suggested price:** ${self.listing['price']:.2f} "
              f"(est. fees ${self.listing['estimated_fees']:.2f}, est. net ${self.listing['estimated_net']:.2f})",
              f"_Pricing basis: {self.listing['rationale']}_", "",
              "**Tags (13 max):** " + ", ".join(self.listing["tags"]), "", "## Description", "",
              self.listing["description"]]
        (self.root / "listing" / "listing.md").write_text("\n".join(md), encoding="utf-8")
        sizes_lines = [f"- {PRODUCT_SPECS[t]['label']}: {w}x{h}px" for t, (w, h) in sizes.items()]
        packager.write_docs(self.product_dir, self.sku, self.listing["title"], self.settings["shop_name"], sizes_lines)

    def make_previews(self):
        try:
            from . import previews
        except ImportError:
            return
        try:
            for p in previews.build_all(self):
                self.record("preview", "", p, validate.check_image(p))
        except Exception as e:
            self.err("previews", f"{e}\n{traceback.format_exc(limit=3)}")

    def make_marketing(self):
        try:
            from . import marketing
        except ImportError:
            return
        try:
            for p in marketing.build_all(self):
                res = validate.check_video(p) if p.suffix == ".mp4" else (
                    validate.check_image(p) if p.suffix == ".png" else {"ok": True, "issues": []})
                self.record("marketing", "", p, res)
        except Exception as e:
            self.err("marketing", f"{e}\n{traceback.format_exc(limit=3)}")

    def package(self):
        max_mb = self.settings["max_zip_mb"]
        self.zips = packager.package(self.product_dir, self.root / "dist", self.sku, max_mb)
        for z in self.zips:
            self.record("zip", "", z, validate.check_zip(z, max_mb))

    # ----------------------------------------------------------- main
    def run(self) -> int:
        t0 = time.process_time()
        w0 = time.time()
        self.prepare()
        self.log(f"Building {self.sku}: '{self.job['theme']}' x {len(self.palettes)} colors "
                 f"[{', '.join(self.job['product_types'])}]")
        self.render_static()
        self.render_video()
        self.make_listing()
        self.make_previews()
        self.make_marketing()
        self.package()
        ok_files = sum(f["ok"] for f in self.files)
        report = {"sku": self.sku, "files_checked": len(self.files), "files_ok": ok_files,
                  "errors": self.errors, "files": self.files}
        (self.root / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        product = {
            "job_id": self.job["id"], "sku": self.sku, "theme": self.job["theme"],
            "category": self.profile["category"], "title": self.listing["title"],
            "description": self.listing["description"], "tags": self.listing["tags"],
            "price": self.listing["price"], "status": "draft", "bundle_dir": str(self.root),
            "zip_files": [_rel(z, self.root) for z in self.zips],
            "palettes": [p.to_dict() for p in self.palettes],
            "valid": int(not self.errors),
            "validation": {"files_checked": len(self.files), "files_ok": ok_files, "errors": self.errors},
            "render_seconds": round(time.time() - w0, 1),
        }
        pid = db.upsert_product(product)
        db.replace_files(pid, self.files)
        cpu = time.process_time() - t0
        cost = cpu / 3600 * self.settings["compute_cost_per_hour"]
        db.add_cost("compute", round(cost, 4), f"render {self.sku} ({cpu:.0f}s CPU)", pid, auto=True)
        self.cpu_seconds = cpu
        self.log(f"  -> {self.sku}: {ok_files}/{len(self.files)} files valid, {len(self.errors)} issue(s), "
                 f"{len(self.zips)} zip(s), {time.time() - w0:.0f}s")
        return pid


def build_job(job_id: int, run_id=None, log=print) -> int | None:
    job = db.get_job(job_id)
    if not job:
        raise BuildError(f"job {job_id} not found")
    db.set_job_status(job_id, "running")
    b = Builder(job, run_id, log)
    try:
        pid = b.run()
        db.set_job_status(job_id, "done")
        return pid
    except Exception as e:
        db.set_job_status(job_id, "failed", str(e))
        db.log_error("build", f"{e}", run_id, job_id)
        log(f"  ! job {job_id} failed: {e}")
        return None


def add_variations(product_id: int, extra: int = 2, run_id=None, log=print) -> int | None:
    """Re-build an (approved) product with more color variations.

    Layout is seeded, so existing variations are reproduced identically and
    new ones are appended.
    """
    p = db.get_product(product_id)
    job = db.get_job(p["job_id"])
    db.execute("UPDATE jobs SET variations=? WHERE id=?", (job["variations"] + extra, job["id"]))
    status = p["status"]
    pid = build_job(job["id"], run_id, log)
    if pid:
        db.set_product_status(pid, status)
    return pid
