#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"
if [ -f ./.env.runtime ]; then
  set -a
  . ./.env.runtime
  set +a
fi
HOST="${NAT_WEBUI_HOST:-0.0.0.0}"
PORT="${NAT_WEBUI_PORT:-8788}"
exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
