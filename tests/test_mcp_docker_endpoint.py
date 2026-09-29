import asyncio
import socket

import pytest

from copia.mcp.data import mcp_client, mcp_endpoint


@pytest.mark.parametrize("address", ["172.20.0.3", "10.0.0.4", "192.168.1.8"])
def test_exact_configured_docker_mcp_endpoint_allows_private_ipv4(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    endpoint = "http://mcp-server:8001/mcp"
    monkeypatch.setenv("COPIA_MCP_TRUSTED_ENDPOINT", endpoint)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 8001))],
    )

    validated = asyncio.run(mcp_endpoint._validate_endpoint(endpoint))

    assert validated.address == address


def test_docker_exception_does_not_allow_other_private_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPIA_MCP_TRUSTED_ENDPOINT", "http://mcp-server:8001/mcp")

    with pytest.raises(mcp_client.McpDiscoveryError):
        asyncio.run(
            mcp_endpoint._validate_endpoint("http://other-service:8001/mcp", allow_local=True)
        )


def test_docker_exception_rejects_metadata_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = "http://mcp-server:8001/mcp"
    monkeypatch.setenv("COPIA_MCP_TRUSTED_ENDPOINT", endpoint)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 8001))
        ],
    )

    with pytest.raises(mcp_client.McpDiscoveryError):
        asyncio.run(mcp_endpoint._validate_endpoint(endpoint))
