# ATC Radar

Live air traffic control radio, transcribed and matched to the aircraft that said it, on a map.
Runs entirely on your own machine. Default home base is Atlanta (KATL tower).

```
audio → split into transmissions → transcribe → find callsign → match to a nearby aircraft → add route → show it
```

## What you get

- **Map** of live aircraft within 30 nm of the airport. Aircraft that just transmitted light up; click one for route, type, tail, altitude and speed.
- **Feed** of every transmission: time, ATC/PILOT, text, matched flight, confidence, and a play button for the clip.
- **Search and filters**, plus ✓/✗ buttons that keep a running "% right" score so you can hand-check the matching.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.json config.json     # edit airport / feed here
./run.sh                               # then open http://localhost:8790
```

Needs Python 3.10+ and `curl`. On Windows, run it in WSL; `ATC Radar.bat` starts it and opens the browser.
The first start downloads the speech model (about 3 GB) and each start takes a couple of minutes to load it.
On a 4-core laptop CPU a transmission takes roughly 9 seconds to transcribe.

## Audio sources

- **Stream URL** set as `source` in `config.json`, or from the GUI ("Stream or file…"). Any MP3/Icecast stream works, including your own RTLSDR-Airband feed.
- **Tab capture** or **mic / line-in** from the GUI (Chrome or Edge), for a scanner or anything you are already listening to.
- **Audio file**, for testing or scoring a recording.

If you point it at a third-party feed such as LiveATC, their terms apply: personal listening only, no redistribution of their audio.

## How matching works

`callsign.py` turns spoken callsigns into ICAO form ("delta fourteen twenty-three" → `DAL1423`, "november five one two alpha bravo" → `N512AB`, "cessna two alpha bravo" → partial `2AB`) and then scores each mention against the aircraft actually nearby (from [adsb.lol](https://adsb.lol)), with small bonuses for aircraft already talking on the frequency and at a plausible altitude. Below the confidence threshold a transmission is left unassigned rather than guessed. Routes come from [adsbdb.com](https://www.adsbdb.com) and are cached in SQLite.

`python test_callsign.py` runs the matcher tests.

## Files

| File | Job |
| --- | --- |
| `ingest.py` | audio sources → one clip per transmission |
| `transcribe.py` | faster-whisper worker (ATC fine-tuned model) |
| `adsb.py` | live aircraft list |
| `callsign.py` | spoken → ICAO, fuzzy match |
| `enrich.py` | route lookups + cache |
| `db.py` | SQLite |
| `main.py` | server + wiring |
| `static/` | the GUI |

## Known rough edges

- A pilot call and the controller's reply often land in one clip, so the ATC/PILOT label is frequently blank.
- GA traffic using short callsigns is the hard case; airline traffic matches much more easily.
- Speech model: [jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper](https://huggingface.co/jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper). Map tiles © OpenStreetMap contributors.
