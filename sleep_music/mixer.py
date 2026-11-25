"""Render a Score to stereo audio: piano + reverb + ambient beds, gentle
levelling, fades, then loudness-normalised export through ffmpeg."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

import numpy as np
from scipy import signal
from scipy.io import wavfile

from . import ambient
from .composer import Score
from .piano import SoftPiano


def render_piano(score: Score, sr: int, seed: int) -> np.ndarray:
    piano = SoftPiano(sr, seed=seed)
    length = int(score.length * sr)
    out = np.zeros((2, length), dtype=np.float32)
    part_gain = {"lh": 0.85, "mel": 1.0, "bell": 0.7}
    for n in score.notes:
        y = piano.note(n.midi, n.vel, n.dur) * part_gain[n.part]
        a = max(0, int(n.time * sr))
        b = min(length, a + len(y))
        if b <= a:
            continue
        # gentle stereo spread by pitch (low = slightly left, high = right)
        pan = np.clip((n.midi - 62) / 45.0, -0.35, 0.35)
        gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        out[0, a:b] += gl * y[: b - a]
        out[1, a:b] += gr * y[: b - a]
    return out


def reverb_ir(sr: int, rng, seconds: float = 3.6, rt60: float = 2.6) -> np.ndarray:
    n = int(seconds * sr)
    t = np.arange(n) / sr
    ir = np.zeros((2, n), dtype=np.float32)
    decay = np.exp(-6.91 * t / rt60)
    bright = signal.butter(2, 5000, "lowpass", fs=sr, output="sos")
    dark = signal.butter(2, 1500, "lowpass", fs=sr, output="sos")
    mix = np.clip(t / 1.5, 0, 1)  # tail gets darker over time, like a warm room
    pre = int(0.022 * sr)
    for ch in range(2):
        w = rng.normal(0, 1, n)
        tail = (1 - mix) * signal.sosfilt(bright, w) + mix * signal.sosfilt(dark, w)
        tail = tail * decay
        tail[:pre] = 0
        tail[pre:pre + int(0.01 * sr)] *= np.linspace(0, 1, int(0.01 * sr))
        ir[ch] = tail
    return ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))


def apply_reverb(x: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    out = np.empty_like(x)
    for ch in range(2):
        r = signal.oaconvolve(x[ch], ir[ch])[: x.shape[1]].astype(np.float32)
        out[ch] = (1 - wet) * x[ch] + wet * r
    return out


def level(x: np.ndarray, sr: int, max_db: float = 4.0) -> np.ndarray:
    """Very slow automatic gain riding for a consistent overall volume."""
    mono = x.mean(axis=0).astype(np.float64)
    hop = sr // 2
    n_hops = len(mono) // hop + 1
    pad = np.zeros(n_hops * hop)
    pad[: len(mono)] = mono
    ms = (pad.reshape(n_hops, hop) ** 2).mean(axis=1)
    k = 25  # ~12 s smoothing window
    ms_s = np.convolve(np.pad(ms, (k, k), mode="edge"), np.ones(2 * k + 1) / (2 * k + 1),
                       mode="valid")
    rms = np.sqrt(ms_s + 1e-12)
    target = np.median(rms)
    lim = 10 ** (max_db / 20)
    gain = np.clip((target / rms) ** 0.7, 1 / lim, lim)
    g = np.interp(np.arange(len(mono)), np.arange(n_hops) * hop + hop / 2, gain)
    return (x * g.astype(np.float32)).astype(np.float32)


def fades(x: np.ndarray, sr: int, fade_in: float, fade_out: float) -> np.ndarray:
    n_in, n_out = int(fade_in * sr), int(fade_out * sr)
    x[:, :n_in] *= (np.sin(np.linspace(0, np.pi / 2, n_in)) ** 2).astype(np.float32)
    x[:, -n_out:] *= (np.cos(np.linspace(0, np.pi / 2, n_out)) ** 2).astype(np.float32)
    return x


def mix_track(score: Score, sr: int, seed: int, ambience: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed + 7)
    length = int(score.length * sr)
    piano = render_piano(score, sr, seed)
    pad = ambient.warm_pad(score.chords, length, sr, rng)
    ocean = ambient.ocean_swell(length, sr, rng)
    air = ambient.air_hush(length, sr, rng)

    p_peak = np.percentile(np.abs(piano), 99.9) + 1e-9
    piano /= p_peak
    mix = piano + pad * 0.16 * ambience
    mix = apply_reverb(mix, reverb_ir(sr, rng), wet=0.32)
    mix += ocean * 0.10 * ambience + air * 0.018 * ambience

    # warm master tone: remove rumble, soften the top end
    sos = np.vstack([signal.butter(2, 32, "highpass", fs=sr, output="sos"),
                     signal.butter(1, 6500, "lowpass", fs=sr, output="sos")])
    mix = signal.sosfilt(sos, mix, axis=1).astype(np.float32)
    mix = level(mix, sr)
    fade_out = min(14.0, score.length * 0.12)
    mix = fades(mix, sr, fade_in=min(6.0, score.length * 0.06), fade_out=fade_out)
    return mix / (np.max(np.abs(mix)) + 1e-9) * 0.9


def export(mix: np.ndarray, sr: int, path: str, lufs: float = -18.0,
           bitrate: str = "256k", keep_wav: bool = False) -> None:
    """Two-pass EBU R128 loudness normalisation, then MP3 (or WAV) export."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        raw = os.path.join(td, "raw.wav")
        wavfile.write(raw, sr, mix.T.astype(np.float32))
        flt = f"loudnorm=I={lufs}:TP=-2:LRA=7"
        meas = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", raw, "-af",
             flt + ":print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, check=True).stderr
        m = json.loads(meas[meas.rindex("{"): meas.rindex("}") + 1])
        flt2 = (f"{flt}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                f":offset={m['target_offset']}:linear=true,aresample={sr}")
        targets = [path]
        if keep_wav and not path.lower().endswith(".wav"):
            targets.append(os.path.splitext(path)[0] + ".wav")
        for tgt in targets:
            codec = (["-c:a", "pcm_s16le"] if tgt.lower().endswith(".wav")
                     else ["-c:a", "libmp3lame", "-b:a", bitrate])
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", raw, "-af", flt2, *codec, tgt], check=True)
