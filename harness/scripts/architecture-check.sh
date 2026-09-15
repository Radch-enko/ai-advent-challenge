#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
status=0

fail_matches() {
  local message="$1"
  shift
  local output
  output="$(rg -n "$@" 2>/dev/null || true)"
  if [[ -n "$output" ]]; then
    echo "$output" >&2
    echo "ERROR: $message" >&2
    status=1
  fi
}

echo "==> Architecture boundaries"

fail_matches "backend domain and data layers must not depend on the FastAPI API layer" \
  '(^|[.])api([.]| import )|copia[.]api' src/copia/domain src/copia/data -g '*.py'

fail_matches "frontend domain models must not depend on React, data, or UI layers" \
  "from ['\"](react|.*data/|.*ui/)|import ['\"](react|.*data/|.*ui/)" client/src/domain -g '*.ts' -g '*.tsx'

fail_matches "frontend data layer must not depend on UI components" \
  "from ['\"].*ui/|import ['\"].*ui/" client/src/data -g '*.ts' -g '*.tsx'

if [[ "$status" -eq 0 ]]; then
  echo "Architecture checks passed."
else
  echo "Architecture checks failed." >&2
fi

exit "$status"
