"""faster-whisper worker: clip -> text. Prompted with the callsigns of aircraft currently nearby.

One pass costs about the same whatever the clip length (Whisper always encodes a 30 s window), so when
clips are waiting they are packed into one window and split back apart with word timestamps.
"""
import os
import queue
import threading

import numpy as np

RATE = 16000
GAP = np.zeros(int(1.5 * RATE), np.float32)
JUNK = {"", "you", "thank you", "thanks", "bye", "thanks for watching"}


def _norm(audio):
    x = audio.astype(np.float32) / 32768.0
    return x / (float(np.abs(x).max()) or 1.0) * 0.9          # scanner audio is often very quiet


class Transcriber(threading.Thread):
    def __init__(self, cfg, get_prompt, on_text, status):
        super().__init__(daemon=True)
        self.cfg, self.get_prompt, self.on_text, self.status = cfg, get_prompt, on_text, status
        self.q = queue.Queue()
        self.model = None

    def submit(self, audio, ts):
        self.q.put((audio, ts))

    def run(self):
        from faster_whisper import WhisperModel

        self.status("loading", "loading speech model (about 2 minutes)")
        try:
            self.model = WhisperModel(self.cfg["model"], device="cpu", compute_type=self.cfg["compute_type"],
                                      cpu_threads=max(2, (os.cpu_count() or 4) // 2))
        except Exception as e:  # noqa: BLE001
            self.status("error", f"model failed to load: {e}")
            return
        self.status("ready", self.cfg["model"].split("/")[-1])
        while True:
            batch = [self.q.get()]
            total = len(batch[0][0]) / RATE
            while self.q.qsize() >= (1 if len(batch) > 1 else 2) and total + len(self.q.queue[0][0]) / RATE + 1.5 <= 27:
                batch.append(self.q.get())
                total += len(batch[-1][0]) / RATE + 1.5
            try:
                texts = self.transcribe([a for a, _ in batch])
            except Exception as e:  # noqa: BLE001
                self.status("error", f"transcribe failed: {e}")
                continue
            for (audio, ts), text in zip(batch, texts):
                if text.lower().strip(" .!") not in JUNK:
                    self.on_text(audio, ts, text)

    def transcribe(self, clips):
        kw = dict(language="en", beam_size=self.cfg["beam_size"], temperature=0.0, condition_on_previous_text=False,
                  initial_prompt=self.get_prompt() if self.cfg["prompt_callsigns"] else None)
        if len(clips) == 1:
            segs, _ = self.model.transcribe(_norm(clips[0]), without_timestamps=True, **kw)
            return [" ".join(s.text.strip() for s in segs if s.no_speech_prob < 0.8).strip()]
        parts, bounds, t = [], [], 0.0
        for c in clips:
            parts += [_norm(c), GAP]
            bounds.append((t, t + len(c) / RATE))
            t += (len(c) + len(GAP)) / RATE
        segs, _ = self.model.transcribe(np.concatenate(parts), word_timestamps=True, **kw)
        out = [[] for _ in clips]
        for s in segs:
            for w in s.words or []:
                mid = (w.start + w.end) / 2
                k = min(range(len(bounds)), key=lambda i: 0 if bounds[i][0] <= mid <= bounds[i][1]
                        else min(abs(mid - bounds[i][0]), abs(mid - bounds[i][1])))
                out[k].append(w.word.strip())
        return [" ".join(ws) for ws in out]
