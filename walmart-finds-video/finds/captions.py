"""Voiceover sync: turn your script + recorded voiceover into timed caption words.

Three alignment modes (config: voiceover.alignment):
  whisper - word-level timestamps from faster-whisper (most accurate; optional
            install: pip install faster-whisper). Script words keep your exact
            spelling (brand names, prices); whisper supplies the timing.
  speech  - no ML needed. FFmpeg finds where you are speaking vs. pausing and the
            script is spread across the speaking time, weighted by word length.
  auto    - whisper if installed, otherwise speech.
With no voiceover the captions are timed to the default scene lengths so you can
preview the video and read the script along with it.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from dataclasses import dataclass


@dataclass
class Word:
    text: str
    section: str
    start: float = 0.0
    end: float = 0.0


def script_words(sections):
    """sections: list of (section_id, text) -> list[Word] (untimed)."""
    out = []
    for sid, text in sections:
        for tok in text.split():
            out.append(Word(tok, sid))
    return out


def _weight(tok):
    """Rough 'how long does this take to say' weight."""
    letters = sum(c.isalpha() for c in tok)
    digits = sum(c.isdigit() for c in tok)
    w = letters + digits * 3.2 + 1.5
    if tok.endswith((".", "!", "?")):
        w += 2.5
    elif tok.endswith((",", ":", ";", "—")):
        w += 1.2
    return max(w, 2.5)


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def speech_intervals(path, noise_db=-32, min_silence=0.22):
    """Speaking intervals found with FFmpeg's silencedetect."""
    dur = audio_duration(path)
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res)]
    silences = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
    speech, cur = [], 0.0
    for s, e in silences:
        if s - cur > 0.05:
            speech.append((cur, s))
        cur = e
    if dur - cur > 0.05:
        speech.append((cur, dur))
    return speech or [(0.0, dur)], dur


def _spread(words, intervals):
    """Distribute words over the given (start, end) intervals by spoken weight."""
    total_speech = sum(e - s for s, e in intervals)
    weights = [_weight(w.text) for w in words]
    total_w = sum(weights) or 1

    def to_time(x):  # x = seconds of pure speech elapsed
        for s, e in intervals:
            if x <= e - s:
                return s + x
            x -= e - s
        return intervals[-1][1]

    acc = 0.0
    for w, wt in zip(words, weights):
        a = acc / total_w * total_speech
        acc += wt
        b = acc / total_w * total_speech
        w.start, w.end = to_time(a), to_time(b - 1e-4)
    return words


def _clip(intervals, a, b):
    out = [(max(s, a), min(e, b)) for s, e in intervals if e > a and s < b]
    return [(s, e) for s, e in out if e - s > 0.02] or [(a, max(b, a + 0.1))]


def align_speech(words, vo_path):
    intervals, dur = speech_intervals(vo_path)
    _spread(words, intervals)
    # Snap each section boundary to the closest real pause, then re-time the
    # words of every section inside its own stretch of speech.
    secs = []
    for w in words:
        if not secs or secs[-1][0] != w.section:
            secs.append((w.section, []))
        secs[-1][1].append(w)
    gaps = [(intervals[i][1], intervals[i + 1][0]) for i in range(len(intervals) - 1)]
    bounds, used_after = [], 0.0
    for k in range(1, len(secs)):
        est = (secs[k - 1][1][-1].end + secs[k][1][0].start) / 2
        best, score = None, 1e9
        for g0, g1 in gaps:
            mid = (g0 + g1) / 2
            if mid <= used_after or abs(mid - est) > 2.0:
                continue
            sc = abs(mid - est) - 0.8 * (g1 - g0)
            if sc < score:
                best, score = mid, sc
        b = best if best is not None else est
        bounds.append(b)
        used_after = b
    edges = [0.0] + bounds + [dur]
    for k, (_, ws) in enumerate(secs):
        _spread(ws, _clip(intervals, edges[k], edges[k + 1]))
    return words, dur


def _norm(tok):
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def align_whisper(words, vo_path, model_size="base"):
    from faster_whisper import WhisperModel  # optional dependency

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(vo_path), word_timestamps=True, vad_filter=True)
    rec = [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]
    dur = audio_duration(vo_path)
    if not rec:
        raise RuntimeError("whisper heard no words")
    a = [_norm(w.text) for w in words]
    b = [_norm(r[0]) for r in rec]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    timed = [None] * len(words)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            r = rec[blk.b + k]
            timed[blk.a + k] = (r[1], r[2])
    # fill unmatched script words (e.g. "$29.00" vs "twenty nine") by interpolation
    i = 0
    n = len(words)
    while i < n:
        if timed[i] is not None:
            i += 1
            continue
        j = i
        while j < n and timed[j] is None:
            j += 1
        lo = timed[i - 1][1] if i > 0 else (rec[0][1] if j == n or timed[j] is None else max(0.0, timed[j][0] - 0.4 * (j - i)))
        hi = timed[j][0] if j < n else max(lo + 0.3 * (j - i), rec[-1][2])
        span = words[i:j]
        _spread(span, [(lo, max(hi, lo + 0.05))])
        for k, w in enumerate(span):
            timed[i + k] = (w.start, w.end)
        i = j
    for w, (s, e) in zip(words, timed):
        w.start, w.end = s, e
    return words, dur


def align(words, vo_path, mode="auto", model_size="base"):
    if mode in ("auto", "whisper"):
        try:
            res = align_whisper(words, vo_path, model_size)
            print("  captions: synced with faster-whisper word timestamps")
            return res
        except ImportError:
            if mode == "whisper":
                raise SystemExit("alignment: whisper needs `pip install faster-whisper`")
        except Exception as e:  # model download blocked, etc.
            if mode == "whisper":
                raise
            print(f"  captions: whisper unavailable ({e}); using speech detection")
    res = align_speech(words, vo_path)
    print("  captions: synced to detected speech in the voiceover")
    return res


def time_evenly(words, spans, lead=0.18, tail=0.55):
    """No voiceover: time each section's words inside its scene span."""
    by = {}
    for w in words:
        by.setdefault(w.section, []).append(w)
    for sid, ws in by.items():
        s, e = spans[sid]
        _spread(ws, [(s + lead, max(s + lead + 0.3, e - tail))])
    return words


# ------------------------------------------------------------- chunking ----

@dataclass
class Chunk:
    words: list
    start: float
    end: float
    section: str


def _ends(w):
    return w.text.endswith((".", "!", "?", ",", ":", "—", ";"))


def chunk(words, max_words=4, max_chars=22):
    chunks, cur = [], []
    for i, w in enumerate(words):
        too_long = len(cur) >= max_words or len(" ".join(x.text for x in cur + [w])) > max_chars
        # don't strand the last word of a sentence on its own
        if too_long and _ends(w) and len(cur) <= max_words and \
                len(" ".join(x.text for x in cur + [w])) <= max_chars + 8:
            too_long = False
        if cur and (cur[-1].section != w.section or too_long):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w.text.endswith((".", "!", "?", ",", ":", "—", ";")) and len(cur) >= 2:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        start = c[0].start
        nxt = chunks[i + 1][0].start if i + 1 < len(chunks) else None
        end = c[-1].end + 0.35
        if nxt is not None and nxt - c[-1].end < 0.6:
            end = nxt
        if nxt is not None:
            end = min(end, nxt)
        out.append(Chunk(c, start, end, c[0].section))
    return out


def _srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(chunks, path):
    lines = []
    for i, c in enumerate(chunks, 1):
        lines += [str(i), f"{_srt_time(c.start)} --> {_srt_time(c.end)}",
                  " ".join(w.text for w in c.words), ""]
    path.write_text("\n".join(lines))
