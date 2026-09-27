import asyncio

import pytest
from mcp.shared.exceptions import MCPError

from copia.mcp.data import mcp_client


@pytest.mark.parametrize(
    ("nested_error", "expected_code", "expected_message"),
    [
        (
            MCPError(code=-32000, message="Invalid country code: Россия"),
            mcp_client.MCP_PROTOCOL_ERROR,
            "Invalid country code: Россия",
        ),
        (
            TimeoutError("timed out"),
            mcp_client.MCP_TIMEOUT,
            "MCP server did not respond within the allowed time",
        ),
        (
            ValueError("Invalid response format"),
            mcp_client.MCP_PROTOCOL_ERROR,
            "Invalid response format",
        ),
    ],
)
def test_call_tool_unwraps_task_group_error(
    monkeypatch: pytest.MonkeyPatch,
    nested_error: Exception,
    expected_code: str,
    expected_message: str,
) -> None:
    async def validate_endpoint(*args, **kwargs):
        return object()

    async def call_tool(*args, **kwargs):
        raise ExceptionGroup("unhandled errors in a TaskGroup", [nested_error])

    monkeypatch.setattr(mcp_client, "_validate_endpoint", validate_endpoint)
    monkeypatch.setattr(mcp_client, "_call_tool", call_tool)

    with pytest.raises(mcp_client.McpDiscoveryError) as error:
        asyncio.run(mcp_client.call_mcp_tool("https://example.com/mcp", "geocode", {}))

    assert error.value.code == expected_code
    assert error.value.message == expected_message


def test_task_group_error_redacts_nested_credentials() -> None:
    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [ValueError("Authorization: Bearer secret-token")],
    )

    message = mcp_client._safe_protocol_message(error)
    assert message.startswith("Authorization: [REDACTED]")
    assert "secret-token" not in message
