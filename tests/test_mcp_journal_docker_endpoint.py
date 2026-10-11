from __future__ import annotations

import asyncio
import socket

import pytest

from copia.mcp.data import mcp_client, mcp_endpoint


def test_exact_configured_journal_docker_endpoint_allows_private_ipv4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "http://journal-mcp-server:8002/mcp"
    monkeypatch.setenv(
        "COPIA_MCP_TRUSTED_ENDPOINT",
        "http://mcp-server:8001/mcp," + endpoint,
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.5", 8002))],
    )

    validated = asyncio.run(mcp_endpoint._validate_endpoint(endpoint))

    assert validated.address == "172.20.0.5"


def test_journal_docker_endpoint_requires_exact_configured_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "COPIA_MCP_TRUSTED_ENDPOINT",
        "http://mcp-server:8001/mcp,http://journal-mcp-server:8002/mcp",
    )

    with pytest.raises(mcp_client.McpDiscoveryError):
        asyncio.run(mcp_endpoint._validate_endpoint("http://journal-mcp-server:9999/mcp"))


def test_unconfigured_journal_docker_endpoint_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPIA_MCP_TRUSTED_ENDPOINT", "http://mcp-server:8001/mcp")

    with pytest.raises(mcp_client.McpDiscoveryError):
        asyncio.run(mcp_endpoint._validate_endpoint("http://journal-mcp-server:8002/mcp"))
