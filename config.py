"""Settings. Defaults below; override any of them in config.json next to this file."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CLIPS = DATA / "clips"

DEFAULTS = {
    "airport": "KATL",
    "airport_name": "Atlanta",
    "feed": "TWR",                 # label shown on every transmission
    "lat": 33.6407,
    "lon": -84.4277,
    "radius_nm": 30,
    "max_alt_ft": 8000,            # aircraft above this are unlikely to be on this frequency
    "port": 8790,
    "model": "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper",
    "compute_type": "int8",
    "beam_size": 1,
    "prompt_callsigns": False,     # prompting made this ATC-tuned model invent callsigns in testing
    "match_threshold": 0.72,
    "source": None,                # optional auto-start: {"kind": "url"|"file", "value": "..."}
    "vad": {"hang_ms": 350, "min_ms": 500, "max_s": 25, "ratio": 3.0, "floor": 120},
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    p = ROOT / "config.json"
    if p.exists():
        user = json.loads(p.read_text())
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    CLIPS.mkdir(parents=True, exist_ok=True)
    return cfg
