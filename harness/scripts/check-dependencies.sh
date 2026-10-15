#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
[[ -f pyproject.toml ]] || { echo 'ERROR: pyproject.toml is missing.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'ERROR: Python 3 is required.' >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
  echo 'ERROR: Python 3.11+ is required.' >&2; exit 1;
}
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
command -v gitleaks >/dev/null || {
  echo 'ERROR: gitleaks is required for the security gate.' >&2
  exit 1
}
printf 'Dependencies ready.\n'
