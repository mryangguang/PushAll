#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1
PORT="${PORT:-8765}"
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" "$@"
