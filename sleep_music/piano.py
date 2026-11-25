"""Soft felt-style piano synthesizer (pure additive synthesis, no samples).

Each note is built from inharmonic string partials (like a real piano string),
2-3 slightly detuned "strings" per note for natural beating, a two-stage
decay (fast "prompt" sound + long "aftersound"), a soft felt hammer attack and
a pitch/velocity dependent tone colour.  Rendered notes are cached by
(pitch, velocity bucket) so long tracks render quickly.
"""
from __future__ import annotations

import numpy as np

NOTE_RENDER_SECONDS = 11.0
VELOCITY_BUCKETS = 16


def midi_to_hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


class SoftPiano:
    def __init__(self, sr: int = 44100, seed: int = 0, brightness: float = 1.0):
        self.sr = sr
        self.rng = np.random.default_rng(seed)
        self.brightness = brightness
        self._cache: dict[tuple[int, int], np.ndarray] = {}
        self._t = np.arange(int(NOTE_RENDER_SECONDS * sr)) / sr

    # ------------------------------------------------------------------ #
    def _render(self, midi: int, vel: float) -> np.ndarray:
        sr, t = self.sr, self._t
        f0 = midi_to_hz(midi)
        rng = self.rng

        # string stiffness -> stretched (inharmonic) partials
        B = np.clip(1.2e-4 * 2.0 ** ((midi - 60) / 20.0), 2e-5, 1.5e-3)

        # sustain times: bass rings long, treble shorter
        tau_long = np.clip(7.0 * 2.0 ** (-(midi - 48) / 22.0), 1.4, 11.0)
        tau_short = tau_long / 7.0

        n_strings = 1 if midi < 34 else (2 if midi < 46 else 3)
        detune_cents = rng.normal(0.0, 0.55, n_strings)
        detune_cents -= detune_cents.mean()

        # felt hammer: soft playing = darker tone
        cutoff = (900.0 + 2600.0 * vel) * self.brightness
        tilt = 2.3 - 0.9 * vel
        strike = 0.117  # hammer strike point (fraction of string length)

        out = np.zeros_like(t)
        n = 1
        while True:
            fn = n * f0 * np.sqrt(1.0 + B * n * n)
            if fn > min(9000.0, sr * 0.45) or n > 28:
                break
            amp = (1.0 / n ** tilt) / (1.0 + (fn / cutoff) ** 2)
            amp *= 0.55 + 0.45 * abs(np.sin(np.pi * n * strike))
            # higher partials die away faster
            k = 1.0 + 0.32 * (n - 1) + fn / 2500.0
            w = 0.55 + 0.25 * vel  # weight of the fast "prompt" decay
            env = w * np.exp(-t / (tau_short / k)) + (1 - w) * np.exp(-t / (tau_long / k))
            partial = np.zeros_like(t)
            for d in detune_cents:
                fd = fn * 2.0 ** (d * (1 + 0.15 * n) / 1200.0)
                partial += np.sin(2 * np.pi * fd * t + rng.uniform(0, 2 * np.pi))
            out += amp * env * partial / n_strings
            n += 1

        # soft hammer attack (felt): a few ms raised-cosine onset
        att = int(sr * (0.012 - 0.006 * vel))
        out[:att] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, att))

        # gentle low "thump" of the felt hammer & soundboard
        thump_len = int(0.06 * sr)
        noise = rng.normal(0, 1, thump_len)
        for _ in range(3):  # crude repeated smoothing = lowpass
            noise = np.convolve(noise, np.ones(24) / 24, mode="same")
        noise *= np.exp(-np.arange(thump_len) / (0.012 * sr))
        out[:thump_len] += noise * 0.04 * vel

        # loudness: normalise per pitch, then scale with velocity
        peak = np.max(np.abs(out[: int(0.2 * sr)])) + 1e-9
        out = out / peak * (vel ** 1.3)
        return out.astype(np.float32)

    # ------------------------------------------------------------------ #
    def note(self, midi: int, vel: float, dur: float, release: float = 0.45) -> np.ndarray:
        """Return a mono note: key/pedal held `dur` seconds, then damped."""
        vel = float(np.clip(vel, 0.05, 1.0))
        bucket = int(round(vel * (VELOCITY_BUCKETS - 1)))
        key = (int(midi), bucket)
        if key not in self._cache:
            self._cache[key] = self._render(int(midi), bucket / (VELOCITY_BUCKETS - 1))
        base = self._cache[key]

        sr = self.sr
        total = min(len(base), int((dur + release * 5) * sr))
        y = base[:total].copy()
        hold = int(dur * sr)
        if hold < total:
            tail = np.arange(total - hold) / sr
            y[hold:] *= np.exp(-tail / release).astype(np.float32)
        # tiny fade to avoid clicks at the very end
        f = min(256, total)
        y[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
        return y
