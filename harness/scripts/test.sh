#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

[[ -x "$PYTHON" ]] || { echo "ERROR: .venv is missing. Run: ./harness/scripts/check-dependencies.sh" >&2; exit 1; }

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT
cp -R "$ROOT_DIR/src" "$ROOT_DIR/tests" "$ROOT_DIR/pyproject.toml" "$ROOT_DIR/profiles.json" "$TEST_ROOT/"

echo "==> Python tests"
cd "$TEST_ROOT"
PYTHONPATH=src "$PYTHON" -m pytest -q tests -p no:cacheprovider
