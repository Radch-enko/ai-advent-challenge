from datetime import UTC, datetime

import pytest

from copia.data.mcp_connections_repository import (
    McpConnectionConflictError,
    McpConnectionsRepository,
)
from copia.domain.models.mcp import McpConnection


def connection(connection_id: str = "finances") -> McpConnection:
    return McpConnection(
        id=connection_id,
        name="Finances",
        endpoint="http://127.0.0.1:8001/mcp",
        header_name="Authorization",
        header_value_env="COPIA_MCP_FINANCES_TOKEN",
        updated_at=datetime.now(UTC),
    )


def test_repository_round_trip_does_not_persist_secret_value(tmp_path) -> None:
    path = tmp_path / "connections.json"
    repository = McpConnectionsRepository(path)
    stored = connection()

    repository.create(stored)

    assert repository.get("finances") == stored
    assert "COPIA_MCP_FINANCES_TOKEN" in path.read_text(encoding="utf-8")
    assert "secret-value" not in path.read_text(encoding="utf-8")


def test_repository_rejects_duplicate_id(tmp_path) -> None:
    repository = McpConnectionsRepository(tmp_path / "connections.json")
    repository.create(connection())

    with pytest.raises(McpConnectionConflictError):
        repository.create(connection())


def test_connection_requires_scoped_secret_environment_name() -> None:
    with pytest.raises(ValueError):
        McpConnection.model_validate(
            {**connection().model_dump(), "header_value_env": "OPENAI_API_KEY"}
        )
