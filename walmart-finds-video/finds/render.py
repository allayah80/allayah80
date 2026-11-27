"""Frame loop + FFmpeg encoding (1080x1920, H.264 + AAC, no music)."""
from __future__ import annotations

import subprocess
import time

from PIL import Image

from . import looks as L
from .gfx import H, W, text_sprite, place_text
from .scenes import Kit, Scenes
from .timeline import TRANSITION_S


class VariationRenderer:
    def __init__(self, cfg, variation, tl):
        if variation.look not in L.LOOKS:
            raise SystemExit(f"Unknown look '{variation.look}'. Choose: {', '.join(L.LOOKS)}")
        self.cfg, self.var, self.tl = cfg, variation, tl
        self.look = L.LOOKS[variation.look]
        self.kit = Kit(cfg, self.look)
        self.sc = Scenes(cfg, self.look, self.kit, tl)
        self.ai_used = variation.background_image is not None
        self.plate = L.make_background(self.look, variation.background_image)
        self.labels = {}

    def _vis_start(self, k):
        s = self.tl.scenes[k].start
        return s - TRANSITION_S / 2 if k > 0 else 0.0

    def _layer(self, k, t):
        s = self.tl.scenes[k]
        u = t - self._vis_start(k)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if s.kind == "intro":
            self.sc.intro(layer, u, self.var)
        elif s.kind == "product":
            self.sc.product(layer, u, s.index, s.end - self._vis_start(k))
        else:
            self.sc.cta(layer, u)
        return layer

    def _wipe_label(self, k):
        s = self.tl.scenes[k]
        if s.kind != "product":
            return None
        if k not in self.labels:
            spr = text_sprite(f"{s.index + 1:02d}", "sans_xbold", 260, L.INK)
            img = Image.new("RGBA", (spr.img.width, spr.img.height), (0, 0, 0, 0))
            place_text(img, spr, spr.ox, spr.oy)
            self.labels[k] = img
        return self.labels[k]

    def frame(self, t):
        frame = L.background_frame(self.plate, t).copy()
        scenes = self.tl.scenes
        k = max(i for i, s in enumerate(scenes) if s.start <= t or i == 0)
        half = TRANSITION_S / 2
        if k + 1 < len(scenes) and t >= scenes[k + 1].start - half:
            a, b = k, k + 1
        elif k > 0 and t < scenes[k].start + half:
            a, b = k - 1, k
        else:
            a = b = k
        if a == b:
            frame.alpha_composite(self._layer(a, t))
        else:
            p = (t - (scenes[b].start - half)) / TRANSITION_S
            L.transition(self.look, frame, self._layer(a, t), self._layer(b, t), p, self._wipe_label(b))
        self.sc.overlays(frame, t, self.ai_used)
        return frame.convert("RGB")

    def encode(self, out_path, threads=2):
        cfg, tl = self.cfg, self.tl
        fps = cfg.fps
        n = int(round(tl.total * fps))
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
        if cfg.voiceover_file:
            cmd += ["-i", str(cfg.voiceover_file)]
            af = "apad" + (",loudnorm=I=-16:TP=-1.5:LRA=11" if cfg.loudnorm else "")
            cmd += ["-af", af]
        else:
            # silent track so editing apps line up your music/voice easily
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        cmd += ["-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-threads", str(threads),
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{n / fps:.3f}", "-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.time()
        try:
            for f in range(n):
                proc.stdin.write(self.frame(f / fps).tobytes())
                if f % (fps * 5) == 0 and f:
                    print(f"  [{self.var.id}] {f / fps:4.1f}s / {tl.total:.1f}s  ({time.time() - t0:.0f}s elapsed)")
        finally:
            proc.stdin.close()
            proc.wait()
        if proc.returncode:
            raise SystemExit(f"ffmpeg failed for {out_path}")
        return time.time() - t0
