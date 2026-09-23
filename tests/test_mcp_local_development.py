from __future__ import annotations

import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from copia.api import service
from copia.data import mcp_client
from copia.domain.models.mcp import McpDiscoveryResult, McpServerSummary


def run(coroutine):
    return asyncio.run(coroutine)


def _loopback_resolution(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8001))]


def test_loopback_http_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _loopback_resolution)

    with pytest.raises(mcp_client.McpDiscoveryError):
        run(mcp_client._validate_endpoint("http://127.0.0.1:8001/mcp"))

    endpoint = run(
        mcp_client._validate_endpoint(
            "http://127.0.0.1:8001/mcp",
            allow_local=True,
        )
    )
    assert endpoint.address == "127.0.0.1"
    assert endpoint.port == 8001


@pytest.mark.parametrize("endpoint", ["http://10.0.0.1/mcp", "http://0.0.0.0:8001/mcp"])
def test_local_opt_in_does_not_allow_private_or_wildcard_hosts(endpoint) -> None:
    with pytest.raises(mcp_client.McpDiscoveryError):
        run(mcp_client._validate_endpoint(endpoint, allow_local=True))


def test_localhost_must_resolve_only_to_loopback(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8001)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 8001)),
        ],
    )

    with pytest.raises(mcp_client.McpDiscoveryError, match="loopback"):
        run(mcp_client._validate_endpoint("http://localhost:8001/mcp", allow_local=True))


def test_api_allows_local_by_default_and_disables_only_for_exact_false(monkeypatch) -> None:
    captured = []

    async def fake_discovery(endpoint: str, *, allow_local: bool = True):
        captured.append(allow_local)
        return McpDiscoveryResult(
            server=McpServerSummary(name="Local MCP", version="1.0"),
            endpoint=endpoint,
            tools=[],
        )

    monkeypatch.setattr(service, "discover_mcp_tools", fake_discovery)
    client = TestClient(service.app)

    monkeypatch.delenv("COPIA_ALLOW_LOCAL_MCP", raising=False)
    enabled_by_default = client.post(
        "/mcp/discover",
        json={"endpoint": "http://127.0.0.1:8001/mcp"},
    )
    monkeypatch.setenv("COPIA_ALLOW_LOCAL_MCP", "false")
    disabled = client.post(
        "/mcp/discover",
        json={"endpoint": "http://127.0.0.1:8001/mcp"},
    )

    assert enabled_by_default.status_code == 200
    assert disabled.status_code == 200
    assert captured == [True, False]
