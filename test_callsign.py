"""Run: python test_callsign.py"""
from callsign import match, mentions

AC = [
    {"hex": "a1", "flight": "DAL1423 ", "r": "N371DA", "t": "B739", "alt_baro": 1200},
    {"hex": "a2", "flight": "SWA2210 ", "r": "N8626B", "t": "B738", "alt_baro": "ground"},
    {"hex": "a3", "flight": "N512AB  ", "r": "N512AB", "t": "C172", "alt_baro": 900},
    {"hex": "a4", "flight": "N83QM   ", "r": "N83QM", "t": "M20P", "alt_baro": 2500},
    {"hex": "a5", "flight": "DAL1600 ", "r": "N387DA", "t": "B738", "alt_baro": 26000},
    {"hex": "a6", "flight": "JBU91   ", "r": "N979JB", "t": "A321", "alt_baro": 3000},
    {"hex": "a7", "flight": "RPA4512 ", "r": "N402YX", "t": "E75L", "alt_baro": 4000},
]

CASES = [
    ("Delta fourteen twenty-three, runway one left, cleared to land", "a1", "ATC"),
    ("cleared to land one left, delta one four two three", "a1", "PILOT"),
    ("Delta 1423, turn left heading 270", "a1", "ATC"),
    ("Southwest twenty-two ten, taxi via whiskey, hold short runway one niner right", "a2", "ATC"),
    ("November five one two alpha bravo, traffic twelve o'clock", "a3", "ATC"),
    ("Cessna two alpha bravo, follow the Boeing on final", "a3", "ATC"),
    ("left base one right, 2AB", "a3", "PILOT"),
    ("Mooney eight three quebec mike, Atlanta tower", "a4", "ATC"),
    ("JetBlue ninety-one contact departure", "a6", "ATC"),
    ("brickyard forty five twelve line up and wait", "a7", "ATC"),
    ("going to departure, delta 1432", "a1", "PILOT"),          # one transposed digit, same airline
    ("wind three one zero at eight, altimeter three zero one two", None, "?"),
    ("United three fifty, cleared for takeoff", None, "ATC"),    # not nearby -> unassigned
]

bad = 0
for text, want_hex, want_role in CASES:
    r = match(text, AC, max_alt=8000)
    ok = r["hex"] == want_hex and r["role"] == want_role
    bad += not ok
    print(("ok  " if ok else "FAIL"), f"{text[:62]:62}", "->", r["hex"], r["callsign"], r["conf"], r["role"], r["mention"])
print("mentions:", [m["s"] for m in mentions("Delta fourteen twenty-three descend and maintain three thousand")[1]])
print("FAILURES:", bad)
raise SystemExit(bad)
