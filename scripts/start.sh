#!/bin/sh
# Start the API using this project's virtualenv, from any current directory.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "The project virtualenv is missing at:"
  echo "  $ROOT/.venv"
  echo "Create it with:"
  echo "  cd \"$ROOT\""
  echo "  python3.12 -m venv .venv"
  echo "  .venv/bin/pip install -e \".[dev]\""
  exit 1
fi

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "The API is already running."
  echo "  http://127.0.0.1:8000/health/live"
  echo "  http://127.0.0.1:8000/docs"
  echo "Stop it with Ctrl-C in the terminal that started it."
  exit 0
fi

"$PYTHON" -m alembic upgrade head
exec "$PYTHON" -m self_healing_platform
