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

## Making a YouTube video
Turn a short background clip (for example, a 5-second Canva export) and a track
into a 1080p MP4. The clip plays forward, then backward, so the loop never jumps.
```bash
python make_video.py --clip puppy.mp4 --audio tracks/dog_sleep_music_30min_seed2026.mp3 --end 3.2
```
- `--start` / `--end`: use only part of the clip (for example, skip a moment where the dog wakes up)
- `--no-pingpong`: loop the clip forward only, if it already loops seamlessly
- `--maxrate`: video bitrate cap (default 1350k, which keeps a 30-minute video around 350 MB)

A 30-minute video takes about 15–20 minutes to encode on 4 cores.

## Code layout
- `sleep_music/piano.py`: piano synthesizer
- `sleep_music/composer.py`: composition rules (keys, progressions, melodies, form)
- `sleep_music/ambient.py`: pad, ocean swell, and air layers
- `sleep_music/mixer.py`: rendering, reverb, levelling, and export
