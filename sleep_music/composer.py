"""Algorithmic composer: builds an original, seed-driven piece of slow,
consonant bedtime piano music.

Structure
---------
piece    -> several *movements*, each in its own key (smooth modulations to
            the IV or V key, so the outgoing tonic chord is a common chord)
movement -> several *sections* (new melody / returning theme / quiet interlude)
section  -> 4-bar phrases in A A' B A'' form over gentle chord progressions

Everything is generated from scratch by random choices inside musical rules,
so every seed produces a different, original track.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MAJOR = [0, 2, 4, 5, 7, 9, 11]
KEY_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
WARM_KEYS = [0, 2, 3, 5, 7, 8, 10]  # C D Eb F G Ab Bb

# Progressions as scale degrees (0 = I, 1 = ii, ... 5 = vi). One chord per bar.
PROGRESSIONS = [
    [0, 5, 3, 4], [0, 3, 5, 4], [0, 2, 3, 0], [5, 3, 0, 4], [3, 0, 1, 4],
    [0, 5, 1, 4], [0, 4, 5, 3], [3, 4, 2, 5], [0, 3, 0, 4], [5, 1, 4, 0],
    [0, 1, 3, 0], [3, 0, 3, 4], [0, 2, 5, 3], [5, 4, 3, 0],
]

# Melody rhythms: one bar (4 beats) each, durations in beats.
RHYTHMS = [
    [2, 2], [1, 1, 2], [3, 1], [1.5, 0.5, 2], [2, 1, 1], [1, 1, 1, 1],
    [1, 2, 1], [2.5, 0.5, 1], [4], [1, 3],
]
CADENCE_RHYTHMS = [[2, 2], [4], [1, 3], [3, 1]]

LH_PATTERNS = ["rolled", "arp8", "arp4", "sparse", "waltzish"]


@dataclass
class Note:
    time: float
    midi: int
    vel: float
    dur: float
    part: str  # "lh", "mel" or "bell"


@dataclass
class ChordSpan:
    start: float
    end: float
    pcs: list[int]        # pitch classes, root first
    bass: int             # midi bass note


@dataclass
class Score:
    sr_bpm: float
    notes: list[Note] = field(default_factory=list)
    chords: list[ChordSpan] = field(default_factory=list)
    length: float = 0.0
    log: list[str] = field(default_factory=list)


class Composer:
    def __init__(self, seed: int, bpm: float = 50.0):
        self.rng = np.random.default_rng(seed)
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.bar = 4 * self.beat

    # ---------------------------------------------------------------- utils
    def _choice(self, seq, p=None):
        return seq[self.rng.choice(len(seq), p=p)]

    def chord_pcs(self, key: int, degree: int) -> list[int]:
        """Diatonic chord with a warm colour tone (maj7 / m7 / add9 / sus)."""
        s = [(key + MAJOR[(degree + i) % 7]) % 12 for i in range(7)]
        tones = [s[0], s[2], s[4]]
        r = self.rng.random()
        if degree in (0, 3):
            tones.append(s[6] if r < 0.45 else s[1])      # maj7 or add9
        elif degree in (1, 2, 5):
            if r < 0.6:
                tones.append(s[6])                          # m7
        elif degree == 4:
            if r < 0.5:
                tones = [s[0], s[3], s[4]]                  # sus4, no tension
            elif r < 0.8:
                tones.append(s[1])                          # add9
        return tones

    def scale_midis(self, key: int, lo: int, hi: int) -> list[int]:
        return [m for m in range(lo, hi + 1) if (m - key) % 12 in MAJOR]

    # -------------------------------------------------------- left hand
    def left_hand(self, t0: float, pcs: list[int], pattern: str, vel: float,
                  out: list[Note]) -> int:
        root = pcs[0]
        bass = 38 + (root - 38) % 12           # D2..C#3
        if bass > 46:
            bass -= 12
        # open, warm voicing: root, fifth, tenth (+ colour tone)
        upper = sorted({48 + (pc - 48) % 12 for pc in pcs[1:]})
        has_fifth = (root + 7) % 12 in pcs
        voicing = [bass, bass + 7 if has_fifth else bass + 12] + upper
        voicing = sorted(set(voicing))
        bar, beat, rng = self.bar, self.beat, self.rng
        hold = bar + 0.25  # pedal held until just after the next chord

        def add(offset, idx, v):
            idx = min(idx, len(voicing) - 1)
            jitter = rng.normal(0, 0.008)
            out.append(Note(t0 + offset + jitter, voicing[idx],
                            v * rng.uniform(0.92, 1.05), hold - offset, "lh"))

        if pattern == "rolled":
            for i in range(len(voicing)):
                add(i * 0.09, i, vel * (1.0 if i == 0 else 0.8))
            add(2 * beat, len(voicing) - 1, vel * 0.6)
        elif pattern == "arp8":
            order = [0, 1, 2, 3, 2, 1, 2, 1]
            for i, idx in enumerate(order):
                add(i * beat / 2, idx, vel * (1.0 if i == 0 else 0.72))
        elif pattern == "arp4":
            order = [0, 2, 1, 3]
            for i, idx in enumerate(order):
                add(i * beat, idx, vel * (1.0 if i == 0 else 0.78))
        elif pattern == "sparse":
            add(0, 0, vel)
            add(0.08, 1, vel * 0.7)
            add(2.5 * beat, 2, vel * 0.6)
            add(3 * beat, 3, vel * 0.55)
        else:  # waltzish: bass then two soft dyads
            add(0, 0, vel)
            add(beat * 1.5, 1, vel * 0.6)
            add(beat * 1.5 + 0.03, 2, vel * 0.55)
            add(beat * 3, 2, vel * 0.5)
            add(beat * 3 + 0.03, 3, vel * 0.45)
        return bass

    # ----------------------------------------------------------- melody
    def make_motif(self, bars: int) -> list[list[tuple[float, float, int]]]:
        """A motif = per bar list of (onset_beat, dur_beats, step)."""
        steps = [-3, -2, -1, 0, 1, 2, 3, 4, -4]
        w = np.array([0.04, 0.17, 0.27, 0.06, 0.27, 0.13, 0.03, 0.015, 0.015])
        w /= w.sum()
        motif = []
        for b in range(bars):
            pool = CADENCE_RHYTHMS if b == bars - 1 else RHYTHMS
            rhythm = self._choice(pool)
            onset, bar_notes = 0.0, []
            for d in rhythm:
                bar_notes.append((onset, d, int(self._choice(steps, w))))
                onset += d
            # an occasional breath: drop the last note of a non-final bar
            if b < bars - 1 and len(bar_notes) > 1 and self.rng.random() < 0.15:
                bar_notes = bar_notes[:-1]
            motif.append(bar_notes)
        return motif

    def realize(self, motif, chords_pcs, key, t0, vel, center, out, end_on_tonic,
                start_pitch=None, vary=False):
        scale = self.scale_midis(key, center - 10, center + 10)
        bar, beat, rng = self.bar, self.beat, self.rng
        idx = int(np.argmin([abs(m - (start_pitch or center)) for m in scale]))
        events = []
        for b, bar_notes in enumerate(motif):
            pcs = chords_pcs[b]
            last_bar = b == len(motif) - 1
            for j, (on, d, step) in enumerate(bar_notes):
                if vary and rng.random() < 0.3:
                    step = int(rng.choice([-2, -1, 1, 2]))
                if not (b == 0 and j == 0):
                    idx += step
                # gravitate back toward the centre of the range
                if scale[min(max(idx, 0), len(scale) - 1)] > center + 7:
                    idx -= 2
                elif scale[min(max(idx, 0), len(scale) - 1)] < center - 7:
                    idx += 2
                idx = min(max(idx, 0), len(scale) - 1)
                strong = on in (0, 2)
                final = last_bar and j == len(bar_notes) - 1
                if strong or final:
                    targets = [key % 12] if (final and end_on_tonic) else pcs[:3]
                    cands = [i for i, m in enumerate(scale) if m % 12 in targets]
                    if cands:
                        prev_m = events[-1][1] if events else None
                        idx = min(cands, key=lambda i: abs(i - idx)
                                  + (1.5 if scale[i] == prev_m else 0) - 0.01 * i)
                events.append([t0 + b * bar + on * beat, scale[idx], d * beat, strong])
        # legato with pedal: each note rings into the next
        for i, (t, m, d, strong) in enumerate(events):
            nxt = events[i + 1][0] if i + 1 < len(events) else t + d
            ring = max(d, nxt - t) + 0.6
            pos = i / max(1, len(events) - 1)
            v = vel * (0.86 + 0.14 * np.sin(np.pi * pos)) * (1.0 if strong else 0.88)
            out.append(Note(t + rng.normal(0, 0.012), m, v * rng.uniform(0.95, 1.04),
                            ring, "mel"))
        return events[-1][1] if events else center

    # ----------------------------------------------------------- sections
    def section(self, kind, key, t0, n_bars, score, theme=None, last=False):
        rng = self.rng
        prog_a = self._choice(PROGRESSIONS)
        prog_b = self._choice(PROGRESSIONS)
        pattern = self._choice(LH_PATTERNS)
        lh_vel = rng.uniform(0.22, 0.30)
        mel_vel = rng.uniform(0.34, 0.44)
        center = int(rng.choice([69, 71, 72, 74]))
        if kind == "theme_low":
            center -= 7
        n_phr = n_bars // 4
        form = ["A", "A2", "B", "A3"][:n_phr] if n_phr >= 3 else (["A", "A3"][:n_phr])
        motif_a = theme if theme is not None else self.make_motif(4)
        motif_b = self.make_motif(4)
        new_theme = motif_a
        prev = None
        for p, label in enumerate(form):
            prog = list(prog_b if label == "B" else prog_a)
            final_phrase = p == len(form) - 1
            if final_phrase and last:
                prog[-1] = 0
            pcs_list = [self.chord_pcs(key, d) for d in prog]
            tp = t0 + p * 4 * self.bar
            for b, pcs in enumerate(pcs_list):
                tb = tp + b * self.bar
                bass = self.left_hand(tb, pcs, pattern, lh_vel, score.notes)
                score.chords.append(ChordSpan(tb, tb + self.bar, pcs, bass))
            if kind in ("melody", "theme", "theme_low"):
                motif = motif_b if label == "B" else motif_a
                end_tonic = (label == "A3") and prog[-1] == 0
                prev = self.realize(motif, pcs_list, key, tp, mel_vel, center,
                                    score.notes, end_tonic, start_pitch=prev,
                                    vary=label in ("A2", "A3"))
            else:  # interlude: soft high "bell" chord tones, lots of space
                for b, pcs in enumerate(pcs_list):
                    if rng.random() < 0.6:
                        tb = tp + b * self.bar + self.beat * rng.choice([0.5, 1, 2])
                        pc = int(rng.choice(pcs[1:] if len(pcs) > 1 else pcs))
                        m = 76 + (pc - 76) % 12
                        score.notes.append(Note(tb, m, rng.uniform(0.16, 0.22),
                                                self.bar * 1.2, "bell"))
        score.log.append(f"{t0/60:5.2f} min  {KEY_NAMES[key]:>2} major  {kind:<9} "
                         f"{n_bars:2d} bars  LH={pattern}")
        return new_theme

    # -------------------------------------------------------------- piece
    def compose(self, duration: float) -> Score:
        rng = self.rng
        score = Score(self.bpm)
        tail = min(14.0, duration * 0.12)          # final chord ring-out
        total_bars = max(4, int((duration - tail) / self.bar + 1e-6))
        key = int(rng.choice(WARM_KEYS))
        t, bars_left = 0.0, total_bars - 1        # keep 1 bar for final chord
        first = True
        while bars_left >= 4:
            # one movement in this key
            theme = None
            n_sections = int(rng.integers(3, 6))
            plan = ["intro"] if first else ["bridge"]
            plan += ["theme", "melody", "interlude", "melody", "theme_low",
                     "melody"][:n_sections]
            first = False
            for k_i, kind in enumerate(plan):
                if bars_left < 4:
                    break
                if kind in ("intro", "bridge"):
                    nb = (4 if duration > 180 else 2) if kind == "intro" else 2
                    nb = min(nb, bars_left)
                    for b in range(nb):
                        pcs = self.chord_pcs(key, 0 if b % 2 == 0 else 3)
                        bass = self.left_hand(t, pcs, "rolled", 0.22, score.notes)
                        score.chords.append(ChordSpan(t, t + self.bar, pcs, bass))
                        t += self.bar
                    bars_left -= nb
                    score.log.append(f"{(t - nb*self.bar)/60:5.2f} min  "
                                     f"{KEY_NAMES[key]:>2} major  {kind}")
                    continue
                nb = 16 if bars_left >= 16 + 4 else (bars_left // 4) * 4
                if bars_left - nb < 4:
                    nb = (bars_left // 4) * 4
                last = bars_left - nb < 4 or k_i == len(plan) - 1
                th = self.section(kind, key, t, nb, score,
                                  theme=theme if kind.startswith("theme") and theme else None,
                                  last=last)
                if theme is None and kind.startswith("theme"):
                    theme = th
                t += nb * self.bar
                bars_left -= nb
            # modulate to IV or V key (common-tone pivot)
            if bars_left >= 20:  # only modulate if a full movement follows
                opts = [(key + d) % 12 for d in (5, 7) if (key + d) % 12 in WARM_KEYS]
                key = int(rng.choice(opts or [(key + 7) % 12]))
        # fill any leftover bars + final tonic chord
        while bars_left > 0:
            pcs = self.chord_pcs(key, 3)
            bass = self.left_hand(t, pcs, "rolled", 0.2, score.notes)
            score.chords.append(ChordSpan(t, t + self.bar, pcs, bass))
            t += self.bar
            bars_left -= 1
        pcs = self.chord_pcs(key, 0)
        final_notes: list[Note] = []
        bass = self.left_hand(t, pcs, "rolled", 0.22, final_notes)
        for n in final_notes:
            if n.time > t + 1.0:
                continue  # just the rolled chord
            n.dur = duration - n.time
            score.notes.append(n)
        top = 72 + (key - 72) % 12
        score.notes.append(Note(t + 0.4, top, 0.3, duration - t, "mel"))
        score.chords.append(ChordSpan(t, duration, pcs, bass))
        score.length = duration
        return score
