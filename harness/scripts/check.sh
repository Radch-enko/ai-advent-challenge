#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
./harness/scripts/bootstrap-check.sh
[[ -f pyproject.toml && -d src/code_assistance && -d tests ]] || {
  echo 'ERROR: Python package is not initialized (pyproject.toml, src/code_assistance/, tests/ required).' >&2
  exit 1
}
./harness/scripts/test.sh
./harness/scripts/lint.sh
./harness/scripts/type-check.sh
./harness/scripts/security-check.sh
printf 'Full validation complete.\n'
