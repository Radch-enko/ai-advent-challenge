from pathlib import Path

from fastapi.testclient import TestClient

from copia.api import service
from copia.data.mcp_connections_repository import McpConnectionsRepository
from copia.domain.models.mcp import McpDiscoveryResult, McpServerSummary, McpToolSummary


def test_connection_crud_uses_environment_reference_without_returning_secret(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        service, "mcp_connections", McpConnectionsRepository(tmp_path / "connections.json")
    )
    monkeypatch.setenv("COPIA_MCP_TEST_TOKEN", "secret-value")

    async def discover(connection):
        assert service._mcp_header(connection) == ("Authorization", "secret-value")
        return McpDiscoveryResult(
            server=McpServerSummary(name="Test", version="1"),
            endpoint=connection.endpoint,
            tools=[
                McpToolSummary(name="search", input_schema={"type": "object", "properties": {}})
            ],
        )

    monkeypatch.setattr(service, "_discover_connection", discover)
    client = TestClient(service.app)
    payload = {
        "id": "test",
        "name": "Test",
        "endpoint": "https://example.test/mcp",
        "header_name": "Authorization",
        "header_value_env": "COPIA_MCP_TEST_TOKEN",
    }

    created = client.post("/mcp/connections", json=payload)
    listed = client.get("/mcp/connections")
    tested = client.post("/mcp/connections/test/test")
    deleted = client.delete("/mcp/connections/test")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert tested.status_code == 200
    assert deleted.status_code == 204
    assert "secret-value" not in created.text
    assert created.json()["tools"][0]["input_schema"]["type"] == "object"


def test_connection_rejects_unscoped_secret_environment_name() -> None:
    response = TestClient(service.app).post(
        "/mcp/connections",
        json={
            "id": "test",
            "name": "Test",
            "endpoint": "https://example.test/mcp",
            "header_name": "Authorization",
            "header_value_env": "OPENAI_API_KEY",
        },
    )

    assert response.status_code == 422
