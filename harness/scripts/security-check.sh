#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "ERROR: gitleaks is required. Run: ./harness/scripts/check-dependencies.sh --security-only" >&2
  exit 1
fi

if [[ "${1:-}" == "--staged" ]]; then
  echo "==> Gitleaks staged scan"
  gitleaks git --staged --redact --no-banner "$ROOT_DIR"
  exit 0
fi

[[ $# -eq 0 ]] || { echo "Usage: ./harness/scripts/security-check.sh [--staged]" >&2; exit 1; }

SCAN_DIR="$(mktemp -d)"
trap 'rm -rf "$SCAN_DIR"' EXIT

while IFS= read -r file; do
  [[ -f "$file" ]] || continue
  mkdir -p "$SCAN_DIR/$(dirname "$file")"
  cp "$file" "$SCAN_DIR/$file"
done < <(git ls-files --cached --others --exclude-standard)

echo "==> Gitleaks repository-content scan"
gitleaks dir --redact --no-banner "$SCAN_DIR"
