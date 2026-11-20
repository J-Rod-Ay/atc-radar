"""adsbdb.com route lookups (callsign -> origin/destination/airline), cached in SQLite."""
import asyncio
import re
import time

import callsign as cs_mod
import db

_mem = {}          # callsign -> route dict or None
_todo = []


def cached(cs):
    return _mem.get(cs)


def want(cs):
    """Queue a lookup the first time an airline-style callsign shows up."""
    if not cs or cs in _mem or cs in _todo or not re.fullmatch(r"[A-Z]{3}\d{1,4}[A-Z]{0,2}", cs):
        return
    found, data = db.get_route(cs)
    if found:
        _mem[cs] = data
        if data:
            cs_mod.learn_telephony(cs[:3], data.get("radio"))
    else:
        _todo.append(cs)


async def worker(client, traffic):
    while True:
        if not _todo:
            await asyncio.sleep(1)
            continue
        cs = _todo.pop(0)
        data = None
        try:
            r = await client.get(f"https://api.adsbdb.com/v0/callsign/{cs}")
            if r.status_code == 200:
                fr = r.json()["response"]["flightroute"]
                o, d, al = fr.get("origin") or {}, fr.get("destination") or {}, fr.get("airline") or {}
                data = {
                    "from": o.get("iata_code") or o.get("icao_code"), "from_city": o.get("municipality"),
                    "to": d.get("iata_code") or d.get("icao_code"), "to_city": d.get("municipality"),
                    "airline": al.get("name"), "radio": al.get("callsign"),
                }
            elif r.status_code not in (400, 404):
                await asyncio.sleep(5)                     # rate limited or down: retry this one later
                continue
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
            continue
        _mem[cs] = data
        db.put_route(cs, data, time.time())
        if data:
            cs_mod.learn_telephony(cs[:3], data.get("radio"))
            for a in traffic.ac.values():
                if a["flight"] == cs:
                    a["route"] = data
        await asyncio.sleep(0.5)
