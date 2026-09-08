#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$PROJECT_DIR/.run"

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

stop_owned_process "$RUNTIME_DIR/api.pid"
stop_owned_process "$RUNTIME_DIR/web.pid"

echo "Copia development services stopped."
