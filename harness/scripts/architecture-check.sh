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

legacy_root_layers="$(find src/copia -mindepth 1 -maxdepth 1 -type d \( -name api -o -name domain -o -name data \) -print)"
if [[ -n "$legacy_root_layers" ]]; then
  echo "$legacy_root_layers" >&2
  echo "ERROR: obsolete root api, domain, and data packages must be removed" >&2
  status=1
fi

remaining_root_components="$(find src/copia -maxdepth 1 -type f ! -name '__init__.py' ! -name 'service.py' -print)"
if [[ -n "$remaining_root_components" ]]; then
  echo "$remaining_root_components" >&2
  echo "ERROR: root package may contain only service.py and __init__.py" >&2
  status=1
fi

service_lines="$(wc -l < src/copia/service.py)"
if (( service_lines > 600 )); then
  echo "ERROR: src/copia/service.py has $service_lines lines; limit is 600" >&2
  status=1
fi

fail_matches "service.py must not define models or feature components" \
  '^class[[:space:]]' src/copia/service.py

fail_matches "backend domain, data, and application layers must not depend on the FastAPI API layer" \
  '^[[:space:]]*(from[[:space:]]+([.]+api([.]|[[:space:]])|copia[.]api([.]|[[:space:]]))|import[[:space:]]+copia[.]api([.]|[[:space:]]|$))' src/copia \
  -g '**/domain/**/*.py' -g '**/data/**/*.py' -g '**/application/**/*.py'

fail_matches "feature API must not import application composition" \
  '^[[:space:]]*(from[[:space:]]+copia[.]service[[:space:]]+import|from[[:space:]]+copia[[:space:]]+import[[:space:]]+service|import[[:space:]]+copia[.]service)' src/copia \
  -g '**/api/**/*.py'

fail_matches "tasks domain and application must use canonical task models" \
  'from[[:space:]]+[.]+domain[.]models[.]task[[:space:]]+import' src/copia/tasks \
  -g '**/domain/**/*.py' -g '**/application/**/*.py'

if ! python3 harness/scripts/import-only-module-check.py; then
  status=1
fi

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
