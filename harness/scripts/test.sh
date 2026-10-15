#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || { echo 'ERROR: .venv is missing.' >&2; exit 1; }
cd "$ROOT_DIR"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m pytest -q -p no:cacheprovider tests
