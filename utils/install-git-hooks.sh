#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GIT_ROOT="$(git rev-parse --show-toplevel)"
[[ "$GIT_ROOT" == "$ROOT_DIR" ]] || { echo "ERROR: Copia must be the Git repository root before installing hooks." >&2; exit 1; }
[[ -x harness/git-hooks/pre-commit ]] || { echo "ERROR: pre-commit hook is not executable." >&2; exit 1; }
[[ -x harness/git-hooks/pre-push ]] || { echo "ERROR: pre-push hook is not executable." >&2; exit 1; }

git config core.hooksPath harness/git-hooks
echo "Installed Copia Git hooks."
echo "core.hooksPath=$(git config core.hooksPath)"
