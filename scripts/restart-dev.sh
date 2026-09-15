#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/.run"
API_PID_FILE="$RUNTIME_DIR/api.pid"
WEB_PID_FILE="$RUNTIME_DIR/web.pid"

stop_owned_process() {
  local pid_file="$1"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(<"$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
  rm -f "$pid_file"
}

if [[ ! -x "$PROJECT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Missing Python environment. Run the setup steps from README.md first." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_DIR/client/node_modules" ]]; then
  echo "Missing web dependencies. Run: cd client && npm install" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
stop_owned_process "$API_PID_FILE"
stop_owned_process "$WEB_PID_FILE"

cd "$PROJECT_DIR"
./.venv/bin/uvicorn copia.api.service:app --host 127.0.0.1 --port 8000 >"$RUNTIME_DIR/api.log" 2>&1 &
echo $! >"$API_PID_FILE"

(
  cd "$PROJECT_DIR/client"
  npm run dev -- --host 127.0.0.1 >"$RUNTIME_DIR/web.log" 2>&1
) &
echo $! >"$WEB_PID_FILE"

sleep 1
if ! kill -0 "$(<"$API_PID_FILE")" 2>/dev/null || ! kill -0 "$(<"$WEB_PID_FILE")" 2>/dev/null; then
  echo "A service did not start. Check .run/api.log and .run/web.log." >&2
  exit 1
fi

echo "Copia API: http://127.0.0.1:8000"
echo "Copia web: http://127.0.0.1:5173"
echo "Logs: $RUNTIME_DIR"
