#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

security_only=false
primary_only=false
case "${1:-}" in
  --security-only) security_only=true ;;
  --primary-only) primary_only=true ;;
  "") ;;
  *) echo "Usage: ./harness/scripts/check-dependencies.sh [--security-only|--primary-only]" >&2; exit 1 ;;
esac

ensure_gitleaks() {
  if command -v gitleaks >/dev/null 2>&1; then
    gitleaks version
    return
  fi
  if command -v brew >/dev/null 2>&1; then
    brew install gitleaks
    return
  fi
  echo "ERROR: gitleaks is required. Install it from https://github.com/gitleaks/gitleaks" >&2
  exit 1
}

if [[ "$security_only" == true ]]; then
  ensure_gitleaks
  exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3.11+ is required." >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || { echo "ERROR: Python 3.11+ is required." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm is required." >&2; exit 1; }

[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix client ci

if [[ "$primary_only" != true ]]; then
  ensure_gitleaks
fi

echo "Dependencies ready."
