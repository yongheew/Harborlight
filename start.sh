#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '%s\n' 'Open http://127.0.0.1:8000. Press Ctrl+C to stop.'
exec .venv/bin/python run.py
