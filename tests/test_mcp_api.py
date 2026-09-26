from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.mcp.data.mcp_client import McpDiscoveryError
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult
from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary


def test_mcp_discover_returns_only_safe_tool_summary(monkeypatch) -> None:
    async def fake_discovery(endpoint: str) -> McpDiscoveryResult:
        return McpDiscoveryResult(
            server=McpServerSummary(name="Example MCP", version="1.0.0"),
            endpoint=endpoint,
            tools=[McpToolSummary(name="search", description="Search documents")],
        )

    monkeypatch.setattr(service, "discover_mcp_tools", fake_discovery)

    response = TestClient(service.app).post(
        "/mcp/discover",
        json={"endpoint": "https://example.com/mcp"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "server": {"name": "Example MCP", "version": "1.0.0"},
        "endpoint": "https://example.com/mcp",
        "tools": [{"name": "search", "description": "Search documents"}],
    }


def test_mcp_discover_maps_safe_error_code(monkeypatch) -> None:
    async def fake_discovery(endpoint: str) -> McpDiscoveryResult:
        raise McpDiscoveryError(
            "mcp_redirect_rejected",
            "MCP server redirects are not supported",
        )

    monkeypatch.setattr(service, "discover_mcp_tools", fake_discovery)

    response = TestClient(service.app).post(
        "/mcp/discover",
        json={"endpoint": "https://example.com/mcp"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "mcp_redirect_rejected",
            "message": "MCP server redirects are not supported",
        }
    }


def test_mcp_discover_passes_optional_header(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    async def fake_discovery(
        endpoint: str, *, header_name: str | None = None, header_value: str | None = None
    ) -> McpDiscoveryResult:
        captured.update(
            endpoint=endpoint,
            header_name=header_name,
            header_value=header_value,
        )
        return McpDiscoveryResult(
            server=McpServerSummary(name="Example MCP", version="1.0.0"),
            endpoint=endpoint,
            tools=[],
        )

    monkeypatch.setattr(service, "discover_mcp_tools", fake_discovery)

    response = TestClient(service.app).post(
        "/mcp/discover",
        json={
            "endpoint": "https://example.com/mcp",
            "header_name": "Authorization",
            "header_value": "Bearer token",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "endpoint": "https://example.com/mcp",
        "header_name": "Authorization",
        "header_value": "Bearer token",
    }


@pytest.mark.parametrize(
    ("code", "status_code"),
    [("mcp_auth_required", 401), ("mcp_access_denied", 403)],
)
def test_mcp_discover_maps_auth_errors(monkeypatch, code: str, status_code: int) -> None:
    async def fake_discovery(endpoint: str) -> McpDiscoveryResult:
        raise McpDiscoveryError(code, "MCP authentication failed")

    monkeypatch.setattr(service, "discover_mcp_tools", fake_discovery)

    response = TestClient(service.app).post(
        "/mcp/discover",
        json={"endpoint": "https://example.com/mcp"},
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == {
        "code": code,
        "message": "MCP authentication failed",
    }


def test_mcp_discover_rejects_http_at_request_boundary() -> None:
    response = TestClient(service.app).post(
        "/mcp/discover",
        json={"endpoint": "http://example.com/mcp"},
    )

    assert response.status_code == 422
