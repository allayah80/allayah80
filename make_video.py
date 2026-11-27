#!/usr/bin/env python3
"""Turn a short looping clip (e.g. a Canva export) + a generated track into a
YouTube-ready 1080p MP4.

The clip is played forward then backward ("ping-pong"), so the loop has no
visible jump. Use --start/--end to keep only the calm part of the clip.

Examples
--------
  python make_video.py --clip puppy.mp4 --audio tracks/my_track.mp3
  python make_video.py --clip puppy.mp4 --audio track.mp3 --end 3.2 --out video.mp4
"""
import argparse
import os
import subprocess
import tempfile


def probe(path, entry, stream="v:0"):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream,
                          "-show_entries", entry, "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return out.strip().split("\n")[0].strip(",")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", required=True, help="short background video clip")
    ap.add_argument("--audio", required=True, help="music track (mp3/wav)")
    ap.add_argument("--start", type=float, default=0.0, help="use clip from this second")
    ap.add_argument("--end", type=float, default=None, help="use clip up to this second")
    ap.add_argument("--no-pingpong", action="store_true",
                    help="loop forward only (use if the clip already loops seamlessly)")
    ap.add_argument("--maxrate", default="1350k", help="video bitrate cap (default 1350k)")
    ap.add_argument("--out", default=None, help="output .mp4")
    args = ap.parse_args()

    out = args.out or os.path.join(
        "output", os.path.splitext(os.path.basename(args.audio))[0] + "_video.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    num, den = probe(args.clip, "stream=r_frame_rate").split("/")
    fps = float(num) / float(den)
    duration = float(probe(args.audio, "format=duration", stream="a:0"))

    s = int(round(args.start * fps))
    e = f":end_frame={int(round(args.end * fps))}" if args.end else ""
    scale = "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos," \
            "crop=1920:1080,setsar=1"
    if args.no_pingpong:
        graph = f"[0:v]trim=start_frame={s}{e},setpts=PTS-STARTPTS,{scale}[out]"
    else:
        clip_len = float(probe(args.clip, "format=duration"))
        n = int(round(((args.end or clip_len) - args.start) * fps))
        # backward half skips both turning-point frames so none is shown twice
        graph = (f"[0:v]trim=start_frame={s}{e},setpts=PTS-STARTPTS,{scale},split[a][b];"
                 f"[b]reverse,trim=start_frame=1:end_frame={n - 1},"
                 "setpts=PTS-STARTPTS[r];[a][r]concat=n=2:v=1[out]")

    with tempfile.TemporaryDirectory() as td:
        loop = os.path.join(td, "loop.mp4")
        print("Building seamless loop ...")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.clip,
                        "-filter_complex", graph, "-map", "[out]", "-an",
                        "-c:v", "libx264", "-crf", "14", "-preset", "slow",
                        "-pix_fmt", "yuv420p", loop], check=True)
        print(f"Rendering {duration/60:.1f}-minute video (this takes a while) ...")
        fade_out = max(0.0, duration - 10)
        subprocess.run([
            "ffmpeg", "-v", "error", "-stats", "-y", "-stream_loop", "-1", "-i", loop,
            "-i", args.audio, "-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}",
            "-vf", f"fade=t=in:st=0:d=3,fade=t=out:st={fade_out:.3f}:d=10",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-maxrate", args.maxrate, "-bufsize", "3400k", "-pix_fmt", "yuv420p",
            "-g", "60", "-r", f"{fps:g}", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            "-movflags", "+faststart", out], check=True)
    print(f"Done -> {out}")


if __name__ == "__main__":
    main()
