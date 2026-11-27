# Dog Sleep Music Generator

Generates original, calm instrumental tracks for dog sleep / relaxation videos.
Everything is synthesized from scratch in Python: no samples, no loops, and no
existing songs.

**Preview:** [`previews/dog_sleep_preview_60s.mp3`](previews/dog_sleep_preview_60s.mp3) (seed 2026)

## What's in a track
| Layer | How it's made |
|---|---|
| Soft piano | Additive synthesis of inharmonic string partials, 2–3 detuned strings per note, two-stage piano decay, felt-hammer attack, sustain pedal |
| Melodies | New motifs for each section in A A′ B A″ phrase form, plus a theme for each movement that comes back later |
| Harmony | Warm diatonic progressions (maj7 / add9 / m7 / sus), broken-chord left hand (5 accompaniment patterns) |
| Ambience | A chord pad that follows the harmony, a slow distant-ocean swell, and a faint airy hush |
| Mix | Synthetic warm-room reverb, gentle high-cut, slow automatic level riding, long fades, two-pass EBU R128 loudness normalization |

Default tempo is 50 BPM. Movements change key smoothly (to the IV or V key), and
there are no drums, vocals, or sudden sounds.

## Setup
Requires Python 3.9+ and [ffmpeg](https://ffmpeg.org/) on your PATH.
```bash
pip install -r requirements.txt
```

## Usage
```bash
python generate_track.py --preview              # 60-second preview
python generate_track.py --minutes 30           # 30-minute track, random seed
python generate_track.py --minutes 30 --seed 42 # reproducible: same seed = same track
python generate_track.py --minutes 60 --bpm 48 --wav --out output/night1.mp3
```
| Option | Default | Meaning |
|---|---|---|
| `--minutes` | 30 | Track length |
| `--seed` | random | Each seed is a different piece; it's printed so you can regenerate it |
| `--bpm` | 50 | Tempo |
| `--ambience` | 1.0 | Ambient layer level (0 = piano only, 1.5 = more ambience) |
| `--lufs` | -18 | Target loudness |
| `--bitrate` | 256k | MP3 bitrate |
| `--wav` | off | Also save a 16-bit WAV master |

A 30-minute track takes about 4 minutes to render on a 4-core machine and needs about 3 GB of RAM.

## Code layout
- `sleep_music/piano.py`: piano synthesizer
- `sleep_music/composer.py`: composition rules (keys, progressions, melodies, form)
- `sleep_music/ambient.py`: pad, ocean swell, and air layers
- `sleep_music/mixer.py`: rendering, reverb, levelling, and export

---

Also in this repo: [`walmart-finds-video/`](walmart-finds-video/), the @thelayahedit vertical shopping video generator.
