#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

[[ -x "$PYTHON" ]] || { echo "ERROR: .venv is missing. Run: ./harness/scripts/check-dependencies.sh" >&2; exit 1; }

cd "$ROOT_DIR"
echo "==> Ruff lint"
"$PYTHON" -m ruff check src tests

echo "==> Ruff format check"
"$PYTHON" -m ruff format --check src tests

echo "==> ESLint"
npm --prefix client run lint

echo "==> Prettier format check"
npm --prefix client run format:check
