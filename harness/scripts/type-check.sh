#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

[[ -x "$PYTHON" ]] || { echo "ERROR: .venv is missing. Run: ./harness/scripts/check-dependencies.sh" >&2; exit 1; }

cd "$ROOT_DIR"
echo "==> Scoped strict mypy check"
"$PYTHON" -m mypy --strict --ignore-missing-imports \
    src/copia/common/configuration.py \
    src/copia/providers/domain/errors.py \
    src/copia/agents/application/agent_runtime.py \
    src/copia/providers/application/llm_router.py \
    src/copia/providers/data/llm.py \
    src/copia/providers/data/openai_provider.py \
    src/copia/providers/data/gigachat_provider.py \
    src/copia/sessions/domain/services/context_strategy.py \
    src/copia/sessions/domain/services/context_rendering.py \
    src/copia/mcp/data/mcp_endpoint.py \
    src/copia/mcp/data/mcp_transport.py \
    src/copia/mcp/data/mcp_client.py
