#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

"$ROOT_DIR/harness/scripts/build-check.sh"
"$ROOT_DIR/harness/scripts/test.sh"
"$ROOT_DIR/harness/scripts/lint.sh"
"$ROOT_DIR/harness/scripts/security-check.sh"
"$ROOT_DIR/harness/scripts/architecture-check.sh"

echo "Full validation complete."
