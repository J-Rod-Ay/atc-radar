"""ATC radar: live ATC audio -> transcript -> matched flight, with a map + feed GUI.

Run:  ./run.sh   then open http://localhost:8790
"""
import asyncio
import json
import os
import time
import wave
from contextlib import asynccontextmanager

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

import callsign
import config
import db
from adsb import Traffic
from ingest import RATE, Segmenter, StreamSource, resample
from transcribe import Transcriber

cfg = config.load()
clients = set()
loop = None
state = {"source": {"kind": "none", "state": "idle", "msg": "no audio source"},
         "model": {"state": "loading", "msg": ""}, "queue": 0}
recent = {}            # hex -> last time it was matched on this frequency
source_thread = None


def publish(ev):
    """Thread-safe broadcast to every connected GUI."""
    if loop is None:
        return
    msg = json.dumps(ev)

    def _send():
        for q in list(clients):
            if q.qsize() < 400:
                q.put_nowait(msg)
    loop.call_soon_threadsafe(_send)


def set_source(state_, msg, kind=None):
    if kind:
        state["source"]["kind"] = kind
    state["source"].update(state=state_, msg=msg)
    publish({"type": "status", **state})


def set_model(state_, msg):
    state["model"].update(state=state_, msg=msg)
    publish({"type": "status", **state})


def on_level(rms, talking):
    publish({"type": "level", "rms": round(rms), "talking": talking})


def on_clip(audio, ts):
    state["queue"] = transcriber.q.qsize() + 1
    transcriber.submit(audio, ts)


def get_prompt():
    acs = sorted(traffic.snapshot(), key=lambda a: a["dist"])
    names = [n for n in (callsign.spoken(a) for a in acs) if n][:30]
    return f"{cfg['airport_name'].lower()} tower, " + ", ".join(names)


def on_text(audio, ts, text):
    acs = traffic.snapshot()
    m = callsign.match(text, acs, recent=recent, now=ts, max_alt=cfg["max_alt_ft"], threshold=cfg["match_threshold"])
    info = None
    if m["hex"]:
        recent[m["hex"]] = ts
        a = next(x for x in acs if x["hex"] == m["hex"])
        info = {k: a.get(k) for k in ("flight", "r", "t", "alt_baro", "gs", "route")}
    tx = {"ts": ts, "dur": round(len(audio) / RATE, 1), "feed": cfg["feed"], "text": text, "role": m["role"],
          "hex": m["hex"], "callsign": m["callsign"], "conf": m["conf"], "mention": m["mention"], "info": info,
          "verdict": None}
    tx["id"] = db.add_tx(tx)
    with wave.open(str(config.CLIPS / f"{tx['id']}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    state["queue"] = transcriber.q.qsize()
    publish({"type": "tx", "tx": tx, "queue": state["queue"]})
    publish({"type": "status", **state})
    who = f"-> {m['callsign']} ({m['conf']:.0%})" if m["hex"] else "-> unassigned"
    print(f"{time.strftime('%H:%M:%S', time.localtime(ts))}  {cfg['feed']}  {m['role']:5}  \"{text}\"  {who}", flush=True)


def start_source(kind, value=None, fast=False):
    global source_thread
    if source_thread:
        source_thread.stop()
        source_thread = None
    segmenter.reset()
    if kind in ("url", "file"):
        if kind == "file" and not os.path.exists(value):
            return set_source("error", f"file not found: {value}", kind)
        set_source("connecting", value, kind)
        source_thread = StreamSource(value, segmenter, set_source, live=(kind == "url"), fast=fast)
        source_thread.start()
    elif kind == "browser":
        set_source("running", value or "browser capture", kind)
    else:
        set_source("idle", "no audio source", "none")


traffic = Traffic(cfg, publish)
segmenter = Segmenter(cfg["vad"], on_clip, on_level)
transcriber = Transcriber(cfg, get_prompt, on_text, set_model)


@asynccontextmanager
async def lifespan(app):
    global loop
    loop = asyncio.get_running_loop()
    db.init()
    transcriber.start()
    task = asyncio.create_task(traffic.run())
    if cfg.get("source"):
        start_source(cfg["source"]["kind"], cfg["source"].get("value"), cfg["source"].get("fast", False))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
STATIC = config.ROOT / "static"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/worklet.js")
def worklet():
    return FileResponse(STATIC / "worklet.js", media_type="application/javascript")


@app.get("/api/init")
def api_init():
    pub = {k: cfg[k] for k in ("airport", "airport_name", "feed", "lat", "lon", "radius_nm")}
    return {"cfg": pub, "status": state, "tx": db.recent_tx(300), "ac": traffic.snapshot(),
            "traffic_ok": traffic.ok, "accuracy": db.accuracy()}


@app.post("/api/source")
def api_source(body: dict):
    start_source(body.get("kind", "none"), body.get("value"), bool(body.get("fast")))
    return state["source"]


@app.post("/api/verdict")
def api_verdict(body: dict):
    db.set_verdict(int(body["id"]), body.get("verdict"))
    acc = db.accuracy()
    publish({"type": "verdict", "id": int(body["id"]), "verdict": body.get("verdict"), "accuracy": acc})
    return acc


@app.get("/clips/{tx_id}.wav")
def clip(tx_id: int):
    p = config.CLIPS / f"{tx_id}.wav"
    return FileResponse(p, media_type="audio/wav") if p.exists() else JSONResponse({"error": "gone"}, 404)


@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    await ws.accept()
    q = asyncio.Queue()
    clients.add(q)
    try:
        while True:
            await ws.send_text(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        clients.discard(q)


@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    """The GUI streams captured tab/mic audio here as float32 PCM; the first message says its sample rate."""
    await ws.accept()
    rate = RATE
    try:
        while True:
            msg = await ws.receive()
            if msg.get("text"):
                hello = json.loads(msg["text"])
                rate = int(hello.get("rate", RATE))
                start_source("browser", hello.get("label"))
            elif msg.get("bytes"):
                pcm = np.frombuffer(msg["bytes"], dtype=np.float32) * 32767.0
                await asyncio.to_thread(segmenter.feed, resample(np.clip(pcm, -32768, 32767), rate))
            elif msg.get("type") == "websocket.disconnect":
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if state["source"]["kind"] == "browser":
            start_source("none")


if __name__ == "__main__":
    print(f"ATC radar for {cfg['airport']} -> http://localhost:{cfg['port']}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=cfg["port"], log_level="warning")
