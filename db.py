"""SQLite storage: transmissions + cached route lookups."""
import json
import sqlite3
import threading

from config import DATA

_lock = threading.Lock()
_con = None


def init():
    global _con
    _con = sqlite3.connect(DATA / "atc.db", check_same_thread=False)
    _con.row_factory = sqlite3.Row
    _con.executescript(
        """
        CREATE TABLE IF NOT EXISTS transmissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, dur REAL, feed TEXT, text TEXT, role TEXT,
            hex TEXT, callsign TEXT, conf REAL, mention TEXT,
            info TEXT,            -- JSON snapshot of the matched aircraft at that moment
            verdict TEXT          -- hand check: 'ok' | 'bad' | NULL
        );
        CREATE INDEX IF NOT EXISTS tx_ts ON transmissions(ts);
        CREATE TABLE IF NOT EXISTS routes(callsign TEXT PRIMARY KEY, data TEXT, ts REAL);
        """
    )


def _row(r):
    d = dict(r)
    d["info"] = json.loads(d["info"]) if d.get("info") else None
    return d


def add_tx(tx):
    with _lock:
        cur = _con.execute(
            "INSERT INTO transmissions(ts,dur,feed,text,role,hex,callsign,conf,mention,info) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (tx["ts"], tx["dur"], tx["feed"], tx["text"], tx["role"], tx.get("hex"), tx.get("callsign"),
             tx.get("conf"), tx.get("mention"), json.dumps(tx["info"]) if tx.get("info") else None),
        )
        _con.commit()
        return cur.lastrowid


def recent_tx(limit=300):
    with _lock:
        rows = _con.execute("SELECT * FROM transmissions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def set_verdict(tx_id, verdict):
    with _lock:
        _con.execute("UPDATE transmissions SET verdict=? WHERE id=?", (verdict, tx_id))
        _con.commit()


def accuracy():
    with _lock:
        r = _con.execute(
            "SELECT SUM(verdict='ok') ok, SUM(verdict='bad') bad FROM transmissions WHERE verdict IS NOT NULL"
        ).fetchone()
    return {"ok": r["ok"] or 0, "bad": r["bad"] or 0}


def get_route(callsign):
    """Returns (found_in_cache, data_or_None)."""
    with _lock:
        r = _con.execute("SELECT data FROM routes WHERE callsign=?", (callsign,)).fetchone()
    if r is None:
        return False, None
    return True, json.loads(r["data"]) if r["data"] else None


def put_route(callsign, data, ts):
    with _lock:
        _con.execute("INSERT OR REPLACE INTO routes VALUES(?,?,?)", (callsign, json.dumps(data) if data else None, ts))
        _con.commit()
