from __future__ import annotations

import asyncio
import ipaddress
import socket
from types import SimpleNamespace

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError

from copia.mcp.data import mcp_client


def run(coroutine):
    return asyncio.run(coroutine)


def test_official_sdk_performs_handshake_and_lists_tools_in_process() -> None:
    async def exercise_client() -> tuple[str | None, str | None, str]:
        server = MCPServer("Test MCP", version="1.0.0")

        @server.tool(name="search", description="Search documents")
        def search(query: str) -> str:
            return query

        async with Client(server, mode="legacy", cache=None) as client:
            listing = await client.list_tools()
            assert client.server_info is not None
            return client.server_info.name, client.server_info.version, listing.tools[0].name

    assert run(exercise_client()) == ("Test MCP", "1.0.0", "search")


def test_protocol_error_preserves_server_message_without_unbounded_payload() -> None:
    error = MCPError(code=-32000, message="Unsupported\nprotocol version")

    assert mcp_client._safe_protocol_message(error) == "Unsupported\nprotocol version"

    long_error = MCPError(code=-32000, message="x" * (mcp_client.MAX_ERROR_MESSAGE_LENGTH + 10))
    assert len(mcp_client._safe_protocol_message(long_error)) == mcp_client.MAX_ERROR_MESSAGE_LENGTH


def test_protocol_error_unwraps_exception_group() -> None:
    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [ExceptionGroup("nested", [MCPError(code=-32000, message="Missing Authorization")])],
    )

    assert mcp_client._safe_protocol_message(error) == "Missing Authorization"


def test_request_header_is_validated_without_exposing_value() -> None:
    assert mcp_client._request_headers("Authorization", "Bearer token") == {
        "Authorization": "Bearer token"
    }

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        mcp_client._request_headers("Authorization", "")
    assert error.value.code == mcp_client.MCP_HEADER_REJECTED
    assert "token" not in error.value.message


@pytest.mark.parametrize(
    ("status_code", "expected_code", "message"),
    [
        (401, mcp_client.MCP_AUTH_REQUIRED, "missing required Authorization header"),
        (403, mcp_client.MCP_ACCESS_DENIED, "access denied"),
    ],
)
def test_http_auth_errors_preserve_bounded_response_message(
    status_code: int, expected_code: str, message: str
) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.headers = {"content-length": str(len(message))}
            self.status_code = status_code

        async def aiter_bytes(self):
            yield message.encode()

        async def aclose(self) -> None:
            return None

    class FakeDelegate:
        async def handle_async_request(self, request):
            return FakeResponse()

    transport = object.__new__(mcp_client._LimitedPinnedTransport)
    transport._delegate = FakeDelegate()

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        run(transport.handle_async_request(SimpleNamespace()))
    assert error.value.code == expected_code
    assert error.value.message == message


def test_endpoint_requires_public_https_without_userinfo_or_fragment() -> None:
    for endpoint in (
        "http://example.com/mcp",
        "https://user@example.com/mcp",
        "https://example.com/mcp#fragment",
        "https://127.0.0.1/mcp",
    ):
        with pytest.raises(mcp_client.McpDiscoveryError) as error:
            run(mcp_client._validate_endpoint(endpoint))
        assert error.value.code == mcp_client.MCP_ENDPOINT_REJECTED


def test_dns_validation_rejects_mixed_public_and_private_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", 443)),
        ],
    )

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        run(mcp_client._validate_endpoint("https://public.example/mcp"))
    assert error.value.code == mcp_client.MCP_ENDPOINT_REJECTED


def test_dns_validation_pins_a_public_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2001:4860:4860::8888", 443, 0, 0),
            ),
        ],
    )

    endpoint = run(mcp_client._validate_endpoint("https://public.example/mcp"))
    assert endpoint.address == "2001:4860:4860::8888"
    assert endpoint.hostname == "public.example"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0", "::1", "fc00::1"],
)
def test_blocked_address_categories(address: str) -> None:
    assert mcp_client._is_blocked_address(ipaddress.ip_address(address))


def test_tool_summary_only_keeps_name_and_description_and_truncates_description() -> None:
    page = SimpleNamespace(
        tools=[
            SimpleNamespace(
                name="search", description="x" * (mcp_client.MAX_DESCRIPTION_LENGTH + 10)
            )
        ]
    )

    result = mcp_client._tool_summaries([page])

    assert result[0].name == "search"
    assert len(result[0].description or "") == mcp_client.MAX_DESCRIPTION_LENGTH


def test_tool_count_limit_is_rejected() -> None:
    page = SimpleNamespace(
        tools=[
            SimpleNamespace(name=f"tool-{index}", description=None)
            for index in range(mcp_client.MAX_TOOLS + 1)
        ]
    )

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        mcp_client._tool_summaries([page])
    assert error.value.code == mcp_client.MCP_RESPONSE_TOO_LARGE


def test_tool_listing_follows_sdk_pagination_without_calling_tools() -> None:
    cursors = []

    class FakeClient:
        async def list_tools(self, *, cursor=None):
            cursors.append(cursor)
            return SimpleNamespace(
                tools=[],
                next_cursor="page-2" if cursor is None else None,
            )

    pages = run(mcp_client._list_tool_pages(FakeClient()))

    assert len(pages) == 2
    assert cursors == [None, "page-2"]


def test_tool_call_rejects_response_exceeding_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(model_dump=lambda **kwargs: {"text": "too large"})],
                structured_content=None,
                is_error=False,
            )

    monkeypatch.setattr(mcp_client, "_LimitedPinnedTransport", lambda address: object())
    monkeypatch.setattr(mcp_client.httpx2, "AsyncClient", lambda **kwargs: FakeContext())
    monkeypatch.setattr(mcp_client, "streamable_http_client", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_client, "Client", lambda *args, **kwargs: FakeContext())
    monkeypatch.setattr(mcp_client, "MAX_RESPONSE_BYTES", 5)
    endpoint = mcp_client._ValidatedEndpoint(
        "https://example.com/mcp", "example.com", 443, "8.8.8.8"
    )

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        run(mcp_client._call_tool(endpoint, {}, "search", {}))

    assert error.value.code == mcp_client.MCP_RESPONSE_TOO_LARGE
