"""Audio in -> one clip per radio transmission.

Sources all end up as 16 kHz mono int16 fed into one Segmenter:
  * browser capture (tab audio or mic/line-in) pushed over a websocket by the GUI
  * a stream URL (your own RTLSDR-Airband / Icecast mount, or any feed that allows programmatic clients)
  * a local audio file (for testing and for scoring a recording)

Scanner/airband audio is squelched, so an adaptive energy gate splits transmissions cleanly;
the transcriber's own voice-activity filter then throws away clips that contain no speech.
"""
import collections
import threading
import time

import numpy as np

RATE = 16000
FRAME = 320  # 20 ms


class Segmenter:
    def __init__(self, vad, on_clip, on_level):
        self.vad, self.on_clip, self.on_level = vad, on_clip, on_level
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.rest = np.zeros(0, np.int16)
        self.history = collections.deque(maxlen=750)      # 15 s of frame levels
        self.pre = collections.deque(maxlen=12)           # 240 ms pre-roll
        self.floor = 0.0
        self.clip = None
        self.loud = self.quiet = self.n = 0
        self.clip_ts = 0.0

    def feed(self, samples, now=None):
        now = time.time() if now is None else now
        with self.lock:
            buf = np.concatenate([self.rest, samples])
            nframes = len(buf) // FRAME
            self.rest = buf[nframes * FRAME:]
            for k in range(nframes):
                self._frame(buf[k * FRAME:(k + 1) * FRAME], now - (nframes - k) * FRAME / RATE)

    def _frame(self, fr, t):
        v = self.vad
        rms = float(np.sqrt(np.mean(fr.astype(np.float32) ** 2)))
        self.n += 1
        if self.clip is None:
            self.history.append(rms)
        if self.n % 25 == 0 and self.history:
            self.floor = float(np.percentile(self.history, 20))
        thr = max(self.floor * v["ratio"], v["floor"])
        is_loud = rms > thr
        if self.n % 10 == 0:
            self.on_level(rms, self.clip is not None)
        if self.clip is None:
            self.pre.append(fr)
            self.loud = self.loud + 1 if is_loud else 0
            if self.loud >= 3:
                self.clip = list(self.pre)
                self.clip_ts = t - len(self.clip) * FRAME / RATE
                self.quiet = 0
            return
        self.clip.append(fr)
        self.quiet = 0 if is_loud else self.quiet + 1
        dur = len(self.clip) * FRAME / RATE
        if self.quiet * 20 >= v["hang_ms"] or dur >= v["max_s"]:
            audio = np.concatenate(self.clip[: len(self.clip) - max(self.quiet - 5, 0)])
            if len(audio) / RATE * 1000 >= v["min_ms"]:
                self.on_clip(audio, self.clip_ts)
            self.clip, self.loud, self.quiet = None, 0, 0
            self.pre.clear()


def resample(x, rate):
    """float32/int16 mono at `rate` -> int16 at 16 kHz."""
    x = np.asarray(x, dtype=np.float32)
    if rate == RATE:
        return x.astype(np.int16)
    if rate % RATE == 0:                                   # 48k -> 16k: average groups (cheap low-pass)
        f = rate // RATE
        x = x[: len(x) // f * f].reshape(-1, f).mean(axis=1)
    else:
        n = int(len(x) * RATE / rate)
        x = np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x)
    return x.astype(np.int16)


class StreamSource(threading.Thread):
    """Decode a URL or file with PyAV and feed the segmenter. Reconnects live streams."""

    def __init__(self, target, seg, status, live=True, fast=False):
        super().__init__(daemon=True)
        self.target, self.seg, self.status, self.live, self.fast = target, seg, status, live, fast
        self.stop_flag = threading.Event()

    def stop(self):
        self.stop_flag.set()
        if getattr(self, "proc", None):
            self.proc.kill()

    def _open(self, av):
        """Files open directly. HTTP streams are fetched with curl (identifying honestly as this app) and piped in.
        ffmpeg's and Python's own HTTP clients get refused or dropped by some stream servers; curl is served."""
        if not self.live:
            return av.open(self.target)
        import subprocess

        self.proc = subprocess.Popen(
            ["curl", "-sSL", "--no-buffer", "--fail", "-A", "atc-radar/0.1", "--connect-timeout", "15", self.target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            return av.open(self.proc.stdout)
        except Exception as e:
            self.proc.kill()
            err = self.proc.stderr.read().decode(errors="replace").strip()
            raise RuntimeError(err or str(e)) from e

    def run(self):
        import av

        while not self.stop_flag.is_set():
            try:
                with self._open(av) as c:
                    stream = c.streams.audio[0]
                    rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
                    self.status("running", f"decoding {stream.codec_context.name} audio")
                    t0, fed = time.time(), 0
                    off = float("inf")
                    for frame in c.decode(stream):
                        if self.stop_flag.is_set():
                            return
                        for out in rs.resample(frame):
                            a = out.to_ndarray().reshape(-1)
                            fed += len(a)
                            if self.live:                  # data arrives in bursts: clock by samples, never ahead of now
                                off = min(off, time.time() - fed / RATE)
                                self.seg.feed(a, now=off + fed / RATE)
                            else:                          # file: keep its own clock
                                self.seg.feed(a, now=t0 + fed / RATE)
                                if not self.fast:
                                    time.sleep(max(0.0, t0 + fed / RATE - time.time()))
                if not self.live:
                    self.status("idle", "file finished")
                    return
                self.proc.kill()
                self.status("error", "stream ended, reconnecting")
            except Exception as e:  # noqa: BLE001 - shown in the GUI
                msg = str(e)
                if "403" in msg or "Forbidden" in msg:
                    self.status("error", "the server refused this client (HTTP 403). Use tab capture or your own feed.")
                    return
                self.status("error", f"{type(e).__name__}: {msg[:160]}")
                if not self.live:
                    return
            self.stop_flag.wait(5)
