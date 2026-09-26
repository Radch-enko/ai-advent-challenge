import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from copia.mcp.data.mcp_client import McpDiscoveryError
from copia.mcp.domain.models.mcp_call_result import McpCallResult
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.services.mcp_tool_loop import (
    ResolvedMcpTool,
    ToolExecutionResult,
    encode_tool_result,
)


class McpToolExecutor:
    def __init__(
        self,
        get_connection: Callable[[str], McpConnection | None],
        get_header: Callable[[McpConnection], tuple[str | None, str | None]],
        get_call_tool: Callable[[], Callable[..., Awaitable[McpCallResult]]],
    ) -> None:
        self._get_connection = get_connection
        self._get_header = get_header
        self._get_call_tool = get_call_tool

    def execute(self, tool: ResolvedMcpTool, arguments: dict[str, Any]) -> ToolExecutionResult:
        connection = self._get_connection(tool.connection_id)
        if connection is None:
            raise RuntimeError("MCP connection is unavailable")
        header_name, header_value = self._get_header(connection)
        try:
            result = asyncio.run(
                self._get_call_tool()(
                    connection.endpoint,
                    tool.tool_name,
                    arguments,
                    header_name=header_name,
                    header_value=header_value,
                    allow_local=os.getenv("COPIA_ALLOW_LOCAL_MCP", "true").lower() != "false",
                )
            )
        except McpDiscoveryError as error:
            raise RuntimeError(error.message) from error
        return ToolExecutionResult(
            encode_tool_result(
                {
                    "content": result.content,
                    "structured_content": result.structured_content,
                    "is_error": result.is_error,
                }
            ),
            is_error=result.is_error,
        )
