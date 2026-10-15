#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
git rev-parse --show-toplevel >/dev/null || { echo 'ERROR: initialize a Git repository before security scanning.' >&2; exit 1; }
command -v gitleaks >/dev/null || { echo 'ERROR: gitleaks is required.' >&2; exit 1; }
SCAN_DIR="$(mktemp -d)"
trap 'rm -rf "$SCAN_DIR"' EXIT
while IFS= read -r -d '' file; do
  [[ -f "$file" ]] || continue
  mkdir -p "$SCAN_DIR/$(dirname "$file")"
  cp "./$file" "$SCAN_DIR/$file"
done < <(git ls-files -z --cached --others --exclude-standard)
gitleaks dir --redact --no-banner "$SCAN_DIR"
