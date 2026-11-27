#!/usr/bin/env python3
"""@thelayahedit vertical shopping video generator.

Examples
  python make_videos.py config/walmart_finds_nov2026.yaml            # all 3 variations
  python make_videos.py config/walmart_finds_nov2026.yaml -v bold    # one variation
  python make_videos.py config/walmart_finds_nov2026.yaml --voiceover voiceover/take1.m4a
  python make_videos.py config/walmart_finds_nov2026.yaml --stills 0.5,3,8   # quick PNG checks
  python make_videos.py config/walmart_finds_nov2026.yaml --script   # print the voiceover script
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from finds import config as C
from finds import captions as cap
from finds import timeline


def _render_one(cfg_path, var_id, vo, out_dir, threads):
    cfg = C.load(cfg_path)
    if vo:
        cfg.voiceover_file = Path(vo).resolve()
    from finds.render import VariationRenderer
    tl = timeline.build(cfg)
    var = next(v for v in cfg.variations if v.id == var_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{cfg.slug}_{var.id}.mp4"
    r = VariationRenderer(cfg, var, tl)
    secs = r.encode(out, threads)
    r.frame(min(1.7, tl.total)).save(out.with_name(out.stem + "_cover.png"))
    cap.write_srt(tl.srt_chunks, out.with_suffix(".srt"))
    return str(out), tl.total, secs


def print_script(cfg):
    print("\nVOICEOVER SCRIPT  (read naturally; pause briefly between sections)\n")
    for sid, text in timeline.sections_for(cfg):
        label = {"hook": "HOOK (first 2 s)", "disclosure": "AUDIBLE DISCLOSURE", "cta": "CALL TO ACTION"}.get(sid)
        if not label:
            label = f"PRODUCT {int(sid[1:]) + 1}: {cfg.products[int(sid[1:])].short_name}"
        print(f"[{label}]\n  {text}\n")
    words = sum(len(t.split()) for _, t in timeline.sections_for(cfg))
    print(f"{words} words ≈ {words / 2.6:.0f}-{words / 2.3:.0f} s at a relaxed pace (aim for 20-30 s total)\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("-v", "--variation", action="append", help="render only this variation id (repeatable)")
    ap.add_argument("--voiceover", help="audio file of your recorded voiceover (overrides config)")
    ap.add_argument("--out", help="output folder (default: from config)")
    ap.add_argument("--stills", help="comma-separated times (s): save PNG frames instead of video")
    ap.add_argument("--script", action="store_true", help="print the voiceover script and exit")
    ap.add_argument("--jobs", type=int, default=3, help="variations rendered in parallel")
    args = ap.parse_args()

    try:
        cfg = C.load(args.config)
    except C.ConfigError as e:
        sys.exit(f"Config problem: {e}")
    if args.voiceover:
        cfg.voiceover_file = Path(args.voiceover).resolve()
    if args.script:
        print_script(cfg)
        return

    out_dir = Path(args.out).resolve() if args.out else cfg.output_dir
    ids = args.variation or [v.id for v in cfg.variations]
    for i in ids:
        if i not in {v.id for v in cfg.variations}:
            sys.exit(f"No variation '{i}'. Available: {', '.join(v.id for v in cfg.variations)}")

    tl = timeline.build(cfg)
    print(f"Timeline: {tl.total:.1f}s  |  " + "  ".join(
        f"{s.kind}{'' if s.kind != 'product' else s.index + 1}@{s.start:.1f}" for s in tl.scenes))

    if args.stills:
        from finds.render import VariationRenderer
        out_dir.mkdir(parents=True, exist_ok=True)
        for v in cfg.variations:
            if v.id not in ids:
                continue
            r = VariationRenderer(cfg, v, tl)
            for t in [float(x) for x in args.stills.split(",")]:
                p = out_dir / f"still_{v.id}_{t:05.2f}s.png"
                r.frame(t).save(p)
                print("  saved", p)
        return

    threads = max(1, 6 // max(1, min(args.jobs, len(ids))))
    with ProcessPoolExecutor(max_workers=max(1, min(args.jobs, len(ids)))) as ex:
        futs = [ex.submit(_render_one, args.config, i, args.voiceover, out_dir, threads) for i in ids]
        for f in futs:
            path, dur, secs = f.result()
            print(f"✓ {path}  ({dur:.1f}s video, rendered in {secs:.0f}s)")


if __name__ == "__main__":
    main()
