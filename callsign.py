"""Spoken callsign -> ICAO normalisation, and fuzzy matching against the nearby-aircraft list.

The parse is never trusted on its own: every mention found in the transcript is scored against
each aircraft that is actually nearby, and the best one wins if it clears the threshold.
"""
import re

from rapidfuzz import fuzz

# radio telephony name -> ICAO airline code (first name listed per code is used for prompting)
TELEPHONY = {
    "american": "AAL", "delta": "DAL", "united": "UAL", "southwest": "SWA", "south west": "SWA",
    "jetblue": "JBU", "jet blue": "JBU", "spirit": "NKS", "spirit wings": "NKS", "frontier": "FFT",
    "frontier flight": "FFT", "alaska": "ASA", "allegiant": "AAY", "sun country": "SCX", "hawaiian": "HAL",
    "moxy": "MXY", "moxie": "MXY", "foxy": "MXY", "avelo": "VXP", "silver wings": "SIL", "fedex": "FDX", "fed ex": "FDX",
    "ups": "UPS", "giant": "GTI", "abex": "ABX", "air transport": "ATN", "connie": "CKS", "polar": "PAC",
    "brickyard": "RPA", "brick yard": "RPA", "envoy": "ENY", "endeavor": "EDV", "skywest": "SKW",
    "sky west": "SKW", "blue streak": "JIA", "bluestreak": "JIA", "piedmont": "PDT", "air shuttle": "ASH",
    "lindbergh": "GJS", "horizon": "QXE", "wisconsin": "AWI", "commutair": "UCA", "compass": "CPZ",
    "execjet": "EJA", "exec jet": "EJA", "flexjet": "LXJ", "flex jet": "LXJ", "jet speed": "EJM",
    "jet linx": "JTL", "twilight": "TWY", "vista": "VJA", "up jet": "UJC", "cair": "KAP", "wiggins": "WIG",
    "martex": "MRA", "amflight": "AMF", "empire": "CFS", "mountain": "MTN", "contour": "VTE",
    "air canada": "ACA", "rouge": "ROU", "jazz": "JZA", "westjet": "WJA", "west jet": "WJA",
    "air transat": "TSC", "sunwing": "SWG", "porter": "POE", "cargojet": "CJT", "flair": "FLE",
    "speedbird": "BAW", "speed bird": "BAW", "virgin": "VIR", "lufthansa": "DLH", "ocean": "OCN",
    "air france": "AFR", "klm": "KLM", "iberia": "IBE", "shamrock": "EIN", "scandinavian": "SAS",
    "air portugal": "TAP", "edelweiss": "EDW", "swiss": "SWR", "austrian": "AUA", "turkish": "THY",
    "emirates": "UAE", "qatari": "QTR", "etihad": "ETD", "iceair": "ICE", "condor": "CFG", "copa": "CMP",
    "avianca": "AVA", "taca": "TAI", "aeromexico": "AMX", "volaris": "VOI", "aeroenlaces": "VIV",
    "caribbean": "BWA", "cayman": "CAY", "bahamas": "BHS", "japan air": "JAL", "all nippon": "ANA",
    "korean air": "KAL", "cathay": "CPA", "azul": "AZU", "medevac": "MED", "lifeguard": "LN",
    "coast guard": "C", "reach": "RCH", "navy": "VV", "army": "R",
}
SPOKEN = {}
for _name, _code in TELEPHONY.items():
    SPOKEN.setdefault(_code, _name)


def learn_telephony(code, name):
    """Add an airline radio name discovered at runtime (adsbdb returns it with each route)."""
    name = re.sub(r"[^a-z ]", "", (name or "").lower()).strip()
    if name and code and name not in TELEPHONY:
        TELEPHONY[name] = code
        SPOKEN.setdefault(code, name)


UNITS = {"zero": "0", "oh": "0", "one": "1", "won": "1", "two": "2", "three": "3", "tree": "3", "four": "4",
         "five": "5", "fife": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "niner": "9"}
TEENS = {"ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
         "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19"}
TENS = {"twenty": "2", "thirty": "3", "forty": "4", "fourty": "4", "fifty": "5", "sixty": "6",
        "seventy": "7", "eighty": "8", "ninety": "9"}
NATO = {"alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E", "foxtrot": "F",
        "fox": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J", "juliett": "J", "kilo": "K",
        "lima": "L", "mike": "M", "november": "N", "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R",
        "sierra": "S", "tango": "T", "uniform": "U", "victor": "V", "whiskey": "W", "whisky": "W",
        "xray": "X", "yankee": "Y", "zulu": "Z"}
# GA make/model words -> ICAO type-code prefixes (only used as a small bonus)
GA_WORDS = {
    "cessna": ("C1", "C2", "C3", "C4", "T2"), "skyhawk": ("C172",), "skylane": ("C182",), "centurion": ("C210",),
    "caravan": ("C208",), "citation": ("C5", "C6", "C7", "C25", "C68"), "cirrus": ("SR2", "SF50", "S22"),
    "piper": ("P28", "PA", "P32", "P46"), "cherokee": ("P28", "PA28"), "archer": ("P28",), "warrior": ("P28",),
    "arrow": ("P28",), "seminole": ("PA44",), "saratoga": ("P32", "PA32"), "malibu": ("P46", "PA46"),
    "navajo": ("PA31",), "comanche": ("PA24", "PA30"), "bonanza": ("BE3",), "baron": ("BE5",),
    "beech": ("BE",), "kingair": ("BE9", "BE20", "B350", "BE30"), "beechjet": ("BE40",), "hawker": ("H25",),
    "mooney": ("M20",), "diamond": ("DA",), "pilatus": ("PC",), "phenom": ("E50", "E55"), "learjet": ("LJ",),
    "lear": ("LJ",), "gulfstream": ("GLF", "G"), "challenger": ("CL",), "falcon": ("F2", "F9", "FA"),
    "global": ("GL",), "helicopter": ("H", "R", "B", "EC", "AS", "S"), "copter": ("H", "R", "B", "EC", "AS", "S"),
    "experimental": (), "skipper": (), "tbm": ("TBM",), "grumman": ("AA",), "tiger": ("AA5",), "husky": ("HUSK",),
    "cub": ("J3", "PA18", "CC"), "robinson": ("R22", "R44", "R66"), "twin": (), "tecnam": ("P2", "P92"),
}
SKIP_BEFORE = {"runway", "heading", "maintain", "altimeter", "squawk", "contact", "wind", "climb", "descend",
               "knots", "departure", "approach", "tower", "ground", "point", "at", "speed", "feet", "thousand"}


def _numlike(t):
    return t.isdigit() or t in UNITS or t in TEENS or t in TENS


def normalize(text):
    """Transcript -> (tokens, items). Items: dicts {k: AIR|NOV|GA|RUN|W, v, i, j} over token span i..j."""
    toks = re.findall(r"[a-z0-9]+", text.lower().replace("-", " ").replace("'", ""))
    items = []
    i, n = 0, len(toks)

    def add_run(piece, idx, letters=False):
        last = items[-1] if items else None
        if last and last["k"] == "RUN" and last["j"] == idx - 1:
            last["v"] += piece
            last["j"] = idx
        else:
            items.append({"k": "RUN", "v": piece, "i": idx, "j": idx})

    while i < n:
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < n else ""
        # airline telephony (1-3 words) directly followed by a number
        hit = None
        for w in (3, 2, 1):
            if i + w <= n:
                ph = " ".join(toks[i:i + w])
                after = toks[i + w] if i + w < n else ""
                if ph in TELEPHONY and _numlike(after):
                    hit = (TELEPHONY[ph], w)
                    break
        if hit:
            items.append({"k": "AIR", "v": hit[0], "i": i, "j": i + hit[1] - 1})
            i += hit[1]
            continue
        if t == "november" and (_numlike(nxt) or re.fullmatch(r"\d+[a-z]{1,2}", nxt)):
            items.append({"k": "NOV", "v": "N", "i": i, "j": i})
        elif t == "king" and nxt == "air":
            items.append({"k": "GA", "v": "kingair", "i": i, "j": i + 1})
            i += 1
        elif t in GA_WORDS and (_numlike(nxt) or nxt in NATO or re.fullmatch(r"\d+[a-z]{1,2}", nxt)):
            items.append({"k": "GA", "v": t, "i": i, "j": i})
        elif t.isdigit():
            add_run(t, i)
        elif t in UNITS:
            add_run(UNITS[t], i)
        elif t in TEENS:
            add_run(TEENS[t], i)
        elif t in TENS:
            if nxt in UNITS and UNITS[nxt] != "0":
                add_run(TENS[t] + UNITS[nxt], i)
                items[-1]["j"] = i + 1
                i += 1
            else:
                add_run(TENS[t] + "0", i)
        elif t in ("hundred", "thousand") and items and items[-1]["k"] == "RUN" and items[-1]["j"] == i - 1:
            items[-1]["v"] += "00" if t == "hundred" else "000"
            items[-1]["j"] = i
        elif t in NATO:
            add_run(NATO[t], i)
        elif re.fullmatch(r"n\d+[a-z]{0,2}", t):          # "n512ab" written out
            items.append({"k": "NOV", "v": "N", "i": i, "j": i})
            items.append({"k": "RUN", "v": t[1:].upper(), "i": i, "j": i})
        elif re.fullmatch(r"\d+[a-z]{1,2}", t):            # "2ab", "19r"
            add_run(t.upper(), i)
        else:
            items.append({"k": "W", "v": t, "i": i, "j": i})
        i += 1
    return toks, items


def mentions(text):
    """All callsign-like mentions in the transcript."""
    toks, items = normalize(text)
    out = []
    used = set()
    for k, it in enumerate(items):
        nx = items[k + 1] if k + 1 < len(items) else None
        follows = nx is not None and nx["k"] == "RUN" and nx["i"] == it["j"] + 1
        if it["k"] == "AIR" and follows:
            m = re.match(r"(\d{1,4})\d*([A-Z]{0,2})", nx["v"])
            if m and m.group(1):
                out.append({"kind": "airline", "s": it["v"] + m.group(1) + m.group(2), "i": it["i"], "j": nx["j"]})
                used.add(k + 1)
        elif it["k"] == "NOV" and follows and 2 <= len(nx["v"]) <= 6:
            out.append({"kind": "reg", "s": "N" + nx["v"][:5], "i": it["i"], "j": nx["j"]})
            used.add(k + 1)
        elif it["k"] == "GA" and follows and 2 <= len(nx["v"]) <= 6:
            out.append({"kind": "partial", "s": nx["v"], "ga": it["v"], "i": it["i"], "j": nx["j"]})
            used.add(k + 1)
    for k, it in enumerate(items):
        if it["k"] != "RUN" or k in used:
            continue
        v = it["v"]
        prev = {toks[x] for x in range(max(0, it["i"] - 2), it["i"])}
        if prev & SKIP_BEFORE:
            continue
        mixed = any(c.isdigit() for c in v) and any(c.isalpha() for c in v)
        if mixed and 3 <= len(v) <= 6:
            out.append({"kind": "partial", "s": v, "ga": None, "i": it["i"], "j": it["j"]})
        elif v.isdigit() and 2 <= len(v) <= 4:
            out.append({"kind": "digits", "s": v, "i": it["i"], "j": it["j"]})
    return toks, out


def _split(cs):
    m = re.fullmatch(r"([A-Z]{2,3})(\d{1,4}[A-Z]{0,2})", cs or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def score(m, ac):
    """How well one mention fits one aircraft, 0..1."""
    cs = (ac.get("flight") or "").strip().upper()
    reg = (ac.get("r") or "").replace("-", "").upper()
    s = m["s"]
    if m["kind"] == "airline":
        if s == cs:
            return 1.0
        p1, n1 = _split(s)
        p2, n2 = _split(cs)
        if not p2:
            return 0.0
        if p1 == p2:
            return 0.5 + 0.42 * fuzz.ratio(n1, n2) / 100
        return 0.8 if n1 == n2 and len(n1) >= 3 else 0.0
    if m["kind"] == "reg":
        best = 0.0
        for cand in {cs, reg}:
            if cand.startswith("N"):
                if cand == s:
                    return 1.0
                if len(s) >= 4 and cand.endswith(s[1:]):       # "November 2AB" short form
                    best = max(best, 0.86)
                best = max(best, 0.45 + 0.45 * fuzz.ratio(s, cand) / 100)
        return best
    if m["kind"] == "partial":
        best = 0.0
        for cand in {cs, reg}:
            if not cand or _split(cand)[0] and not cand.startswith("N"):
                continue                                         # airline flights don't take GA short forms
            body = cand[1:] if cand.startswith("N") else cand
            if body == s:
                best = max(best, 0.97)
            elif len(s) >= 3 and cand.endswith(s):
                best = max(best, 0.88)
            elif len(s) == 2 and cand.endswith(s):
                best = max(best, 0.6)
            elif len(s) >= 4:
                best = max(best, 0.35 + 0.5 * fuzz.ratio(s, body) / 100)
        if best and m.get("ga"):
            typ = (ac.get("t") or "").upper()
            if typ and any(typ.startswith(p) for p in GA_WORDS.get(m["ga"], ())):
                best += 0.05
        return min(best, 1.0)
    if m["kind"] == "digits":
        _, n2 = _split(cs)
        return 0.72 if n2 and n2 == s and len(s) >= 3 else 0.0
    return 0.0


def role_of(m, ntoks):
    """Controllers lead with the callsign, pilots end with it."""
    at_start = m["i"] <= 1
    at_end = m["j"] >= ntoks - 2
    if at_start and not at_end:
        return "ATC"
    if at_end and not at_start:
        return "PILOT"
    return "?"


def match(text, aircraft, recent=None, now=0.0, max_alt=8000, threshold=0.72):
    """Returns {hex, callsign, conf, mention, role, span} (hex None when unassigned)."""
    toks, ms = mentions(text)
    recent = recent or {}
    best = None
    second = 0.0
    for m in ms:
        for ac in aircraft:
            sc = score(m, ac)
            if sc <= 0:
                continue
            if now - recent.get(ac["hex"], -1e9) < 180:
                sc += 0.06                                       # already talking on this frequency
            alt = ac.get("alt_baro")
            if alt == "ground" or (isinstance(alt, (int, float)) and alt <= max_alt):
                sc += 0.03
            elif isinstance(alt, (int, float)):
                sc -= 0.08                                       # far too high for this frequency
            sc = min(sc, 1.0)
            if best is None or sc > best[0]:
                if best and best[2]["hex"] != ac["hex"]:
                    second = max(second, best[0])
                best = (sc, m, ac)
            elif ac["hex"] != best[2]["hex"]:
                second = max(second, sc)
    res = {"hex": None, "callsign": None, "conf": 0.0, "mention": None, "role": "?", "span": None}
    lead = next((m for m in ms if m["kind"] != "digits"), None)
    if lead:
        res.update(mention=lead["s"], role=role_of(lead, len(toks)), span=[lead["i"], lead["j"]])
    if best:
        sc, m, ac = best
        ambiguous = sc < 0.95 and sc - second < 0.04
        res.update(conf=round(sc, 2), mention=m["s"], role=role_of(m, len(toks)), span=[m["i"], m["j"]])
        if sc >= threshold and not ambiguous:
            res.update(hex=ac["hex"], callsign=(ac.get("flight") or "").strip() or ac.get("r"))
    return res


_WORDS = dict(zip("0123456789", "zero one two three four five six seven eight niner".split()))
_LETTERS = {v: k for k, v in reversed(list(NATO.items()))}


def _say(chars):
    return " ".join(_WORDS.get(c) or _LETTERS.get(c, c.lower()) for c in chars)


def spoken(ac):
    """How this callsign sounds on the radio, in the transcriber's own style (used to prompt it)."""
    cs = (ac.get("flight") or "").strip().upper()
    p, n = _split(cs)
    if p and p in SPOKEN:
        return f"{SPOKEN[p]} {_say(n)}"
    reg = ac.get("r") or cs
    if reg and reg.startswith("N") and len(reg) > 2:
        return f"november {_say(reg[1:])}"
    return None
