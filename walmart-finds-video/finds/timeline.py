"""Scene timing. Without a voiceover, scenes use default lengths that fit the
target duration. With a voiceover, each scene starts just before you begin
talking about it, so visuals follow your voice."""
from __future__ import annotations

from dataclasses import dataclass

from . import captions as cap

HOOK_S = 2.4          # hook headline on its own
DISCLOSURE_S = 2.4    # reserved slot for the audible disclosure
CTA_S = 3.4
TRANSITION_S = 0.5


@dataclass
class Scene:
    kind: str          # intro | product | cta
    start: float
    end: float
    index: int = 0     # product index for product scenes


@dataclass
class Timeline:
    scenes: list
    total: float
    disclosure_at: float
    words: list
    chunks: list          # captions drawn on screen
    srt_chunks: list      # every spoken line (for the .srt file)
    has_voiceover: bool


def sections_for(cfg):
    secs = [("hook", cfg.hook_voiceover), ("disclosure", cfg.disclosure_voiceover)]
    secs += [(f"p{i}", p.voiceover) for i, p in enumerate(cfg.products)]
    secs.append(("cta", cfg.cta))
    return [(s, t) for s, t in secs if t]


def build(cfg):
    n = len(cfg.products)
    words = cap.script_words(sections_for(cfg))

    if cfg.voiceover_file:
        words, vo_dur = cap.align(words, cfg.voiceover_file, cfg.alignment, cfg.whisper_model)
        first = {}
        last = {}
        for w in words:
            first.setdefault(w.section, w.start)
            last[w.section] = w.end

        def boundary(prev_ids, sid, fallback):
            if sid not in first:
                return fallback
            prev_end = max((last[p] for p in prev_ids if p in last), default=0.0)
            return max(prev_end + 0.05, first[sid] - 0.25)

        order = ["hook", "disclosure"] + [f"p{i}" for i in range(n)] + ["cta"]
        starts = {"hook": 0.0}
        for k, sid in enumerate(order[1:], 1):
            fb = starts[order[k - 1]] + (DISCLOSURE_S if sid == "disclosure" else 4.0)
            starts[sid] = boundary(order[:k], sid, fb)
        speech_end = max((w.end for w in words), default=vo_dur)
        total = max(vo_dur, speech_end + 1.6, starts["cta"] + 2.2)
        if total < cfg.min_seconds:
            total = cfg.min_seconds
        if total > cfg.max_seconds + 0.01:
            print(f"  WARNING: voiceover makes the video {total:.1f}s (max {cfg.max_seconds:.0f}s). "
                  "Trim the script or speak a little faster.")
        disclosure_at = starts.get("disclosure", HOOK_S)
        p_starts = [starts[f"p{i}"] for i in range(n)]
        cta_start = starts["cta"]
        has_vo = True
    else:
        target = min(max(cfg.target_seconds, cfg.min_seconds), cfg.max_seconds)
        prod_len = max(3.4, (target - HOOK_S - DISCLOSURE_S - CTA_S) / n)
        disclosure_at = HOOK_S
        t = HOOK_S + DISCLOSURE_S
        p_starts = []
        for i in range(n):
            p_starts.append(t)
            t += prod_len
        cta_start = t
        total = min(max(t + CTA_S, cfg.min_seconds), cfg.max_seconds)
        has_vo = False

    scenes = [Scene("intro", 0.0, p_starts[0])]
    for i, s in enumerate(p_starts):
        scenes.append(Scene("product", s, p_starts[i + 1] if i + 1 < n else cta_start, i))
    scenes.append(Scene("cta", cta_start, total))

    if not has_vo:
        spans = {"hook": (0.0, disclosure_at), "disclosure": (disclosure_at, p_starts[0]),
                 "cta": (cta_start, total)}
        for i in range(n):
            spans[f"p{i}"] = (scenes[i + 1].start, scenes[i + 1].end)
        words = cap.time_evenly(words, spans)

    shown = [w for w in words
             if not (w.section == "hook" and not cfg.captions_on_hook)
             and not (w.section == "cta" and not cfg.captions_on_cta)
             # the on-screen disclosure card already shows this text
             and not (w.section == "disclosure" and not cfg.captions_on_disclosure)]
    chunks = cap.chunk(shown) if cfg.captions else []
    return Timeline(scenes, total, disclosure_at, words, chunks, cap.chunk(words), has_vo)
