#!/bin/bash
# Start ATC Radar, then open http://localhost:8790
cd "$(dirname "$0")"
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
[ -x "$HOME/.venvs/atc-radar/bin/python" ] && PY="$HOME/.venvs/atc-radar/bin/python"
exec "$PY" main.py
