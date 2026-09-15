#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLIENT_DIR="$ROOT_DIR/client"

[[ -x "$CLIENT_DIR/node_modules/.bin/tsc" ]] || { echo "ERROR: client dependencies are missing. Run: ./harness/scripts/check-dependencies.sh" >&2; exit 1; }

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> TypeScript typecheck"
cd "$CLIENT_DIR"
npm run typecheck

echo "==> Vite production build"
./node_modules/.bin/vite build --outDir "$BUILD_DIR" --emptyOutDir
