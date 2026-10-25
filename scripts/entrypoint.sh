#!/bin/sh
set -eu
cd /app
python -m alembic -c /app/alembic.ini upgrade head
exec python -m uvicorn self_healing_platform.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
