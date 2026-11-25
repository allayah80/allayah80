"""Gentle ambient layers, all synthesized: a warm chord pad that follows the
harmony, a slow "distant ocean / soft wind" swell and a faint airy hush.
No rain drops, birds or anything with a sudden onset."""
from __future__ import annotations

import numpy as np
from scipy import signal

from .composer import ChordSpan


def _sos(kind, freq, sr, order=2):
    return signal.butter(order, freq, btype=kind, fs=sr, output="sos")


def warm_pad(chords: list[ChordSpan], length: int, sr: int, rng) -> np.ndarray:
    """Stereo pad; equal-power crossfades of ~3 s between chords."""
    out = np.zeros((2, length), dtype=np.float32)
    fade = 3.0
    # merge consecutive identical chords so the pad doesn't re-swell
    merged: list[list] = []
    for c in chords:
        if merged and merged[-1][2] == c.pcs:
            merged[-1][1] = c.end
        else:
            merged.append([c.start, c.end, c.pcs])
    for start, end, pcs in merged:
        s = max(0.0, start - fade / 2)
        e = end + fade / 2
        n = int((e - s) * sr)
        t = np.arange(n) / sr
        seg = np.zeros((2, n), dtype=np.float64)
        root = 48 + (pcs[0] - 48) % 12
        notes = [root, root + 7, root + 12 + (pcs[1] - pcs[0]) % 12]
        if len(pcs) > 3:
            notes.append(root + 12 + (pcs[3] - pcs[0]) % 12)
        for i, m in enumerate(notes):
            f = 440.0 * 2 ** ((m - 69) / 12)
            for ch in range(2):
                det = 2 ** (rng.uniform(-5, 5) / 1200)
                ph = rng.uniform(0, 2 * np.pi)
                w = 2 * np.pi * f * det * t + ph
                tone = np.sin(w) + 0.25 * np.sin(2 * w) + 0.08 * np.sin(3 * w)
                seg[ch] += tone * (0.9 if i == 0 else 0.6)
        env = np.ones(n)
        nf = min(int(fade * sr), n // 2)
        ramp = np.sin(np.linspace(0, np.pi / 2, nf))
        env[:nf] = ramp
        env[-nf:] = ramp[::-1]
        a = int(s * sr)
        b = min(length, a + n)
        out[:, a:b] += (seg * env)[:, : b - a].astype(np.float32)
    out = signal.sosfilt(_sos("lowpass", 1400, sr), out, axis=1).astype(np.float32)
    # slow "breathing" movement
    t = np.arange(length) / sr
    breath = 0.85 + 0.15 * np.sin(2 * np.pi * t / 23.0 + rng.uniform(0, 6))
    return out * breath.astype(np.float32) / (np.max(np.abs(out)) + 1e-9)


def ocean_swell(length: int, sr: int, rng) -> np.ndarray:
    """Low, slowly swelling filtered brown noise - like distant waves/wind."""
    out = np.zeros((2, length), dtype=np.float32)
    t = np.arange(length) / sr
    for ch in range(2):
        white = rng.normal(0, 1, length).astype(np.float32)
        brown = signal.lfilter([1.0], [1.0, -0.995], white).astype(np.float32)
        x = signal.sosfilt(_sos("bandpass", [45, 420], sr), brown).astype(np.float32)
        p1, p2 = rng.uniform(9, 13), rng.uniform(15, 21)
        lfo = (0.62 + 0.25 * np.sin(2 * np.pi * t / p1 + rng.uniform(0, 6))
               + 0.13 * np.sin(2 * np.pi * t / p2 + rng.uniform(0, 6)))
        out[ch] = x * lfo.astype(np.float32)
    return out / (np.max(np.abs(out)) + 1e-9)


def air_hush(length: int, sr: int, rng) -> np.ndarray:
    """Very soft, steady airy hush (think gentle fan / far-off rain)."""
    out = np.zeros((2, length), dtype=np.float32)
    for ch in range(2):
        white = rng.normal(0, 1, length).astype(np.float32)
        pinkish = signal.lfilter([1.0], [1.0, -0.9], white).astype(np.float32)
        out[ch] = signal.sosfilt(_sos("bandpass", [700, 4200], sr), pinkish)
    return out / (np.max(np.abs(out)) + 1e-9)
