"""Live candidate list: poll adsb.lol (fallback airplanes.live) for aircraft near the airport."""
import asyncio
import math
import time

import httpx

import enrich

SOURCES = [
    "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}",
]
KEEP_S = 90      # keep an aircraft this long after its last report (they drop off when they land)


def dist_nm(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 3440.065 * 2 * math.asin(math.sqrt(a))


class Traffic:
    def __init__(self, cfg, publish):
        self.cfg, self.publish = cfg, publish
        self.ac = {}
        self.ok = False

    def snapshot(self):
        return list(self.ac.values())

    async def run(self):
        cfg = self.cfg
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "atc-radar/0.1"}) as client:
            asyncio.create_task(enrich.worker(client, self))
            while True:
                data = None
                for url in SOURCES:
                    try:
                        r = await client.get(url.format(lat=cfg["lat"], lon=cfg["lon"], nm=cfg["radius_nm"]))
                        if r.status_code == 200:
                            data = r.json().get("ac") or []
                            break
                    except Exception:  # noqa: BLE001 - try the next source
                        continue
                now = time.time()
                self.ok = data is not None
                if data is not None:
                    ac = dict(self.ac)
                    for a in data:
                        if a.get("lat") is None:
                            continue
                        cs = (a.get("flight") or "").strip()
                        ac[a["hex"]] = {
                            "hex": a["hex"], "flight": cs, "r": a.get("r"), "t": a.get("t"),
                            "alt_baro": a.get("alt_baro"), "gs": a.get("gs"), "track": a.get("track"),
                            "lat": a["lat"], "lon": a["lon"], "seen": now,
                            "dist": round(dist_nm(cfg["lat"], cfg["lon"], a["lat"], a["lon"]), 1),
                            "route": enrich.cached(cs),
                        }
                        enrich.want(cs)
                    self.ac = {h: v for h, v in ac.items() if now - v["seen"] < KEEP_S}
                self.publish({"type": "traffic", "ok": self.ok, "ac": self.snapshot()})
                await asyncio.sleep(5)
