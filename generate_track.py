#!/usr/bin/env python3
"""Generate an original, calm piano + ambience track for dog sleep music.

Examples
--------
  python generate_track.py --preview                 # 60-second preview
  python generate_track.py --minutes 30 --seed 42    # full 30-minute track
  python generate_track.py --minutes 60 --seed 7 --bpm 48 --wav
"""
import argparse
import random
import time

from sleep_music.composer import Composer
from sleep_music.mixer import export, mix_track

SR = 44100


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=30.0, help="track length (default 30)")
    ap.add_argument("--preview", action="store_true", help="render a 60-second preview")
    ap.add_argument("--seed", type=int, default=None,
                    help="random seed; same seed = same track (default: random)")
    ap.add_argument("--bpm", type=float, default=50.0, help="tempo (default 50)")
    ap.add_argument("--ambience", type=float, default=1.0,
                    help="ambient layer level multiplier (0 = piano only)")
    ap.add_argument("--lufs", type=float, default=-18.0, help="target loudness (default -18)")
    ap.add_argument("--bitrate", default="256k", help="MP3 bitrate (default 256k)")
    ap.add_argument("--wav", action="store_true", help="also write a 16-bit WAV master")
    ap.add_argument("--out", default=None, help="output file (.mp3 or .wav)")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randint(1, 999_999)
    seconds = 60.0 if args.preview else args.minutes * 60.0
    out = args.out or (f"output/{'preview' if args.preview else 'track'}_seed{seed}.mp3")

    t0 = time.time()
    print(f"Composing {seconds/60:.1f} min at {args.bpm:g} BPM (seed {seed}) ...")
    score = Composer(seed, args.bpm).compose(seconds)
    for line in score.log:
        print("  ", line)
    print(f"  {len(score.notes)} piano notes")
    print("Rendering audio ...")
    mix = mix_track(score, SR, seed, ambience=args.ambience)
    print("Normalising loudness and encoding ...")
    export(mix, SR, out, lufs=args.lufs, bitrate=args.bitrate, keep_wav=args.wav)
    print(f"Done in {time.time()-t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
