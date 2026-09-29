import asyncio
import base64
import binascii
from collections.abc import Awaitable, Callable
from typing import Any

from copia.common.configuration import get_settings
from copia.mcp.data.mcp_client import McpDiscoveryError
from copia.mcp.domain.models.mcp_artifact import McpArtifact
from copia.mcp.domain.models.mcp_call_result import McpCallResult
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.services.mcp_tool_loop import (
    ResolvedMcpTool,
    ToolExecutionResult,
    encode_tool_result,
)

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


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
                    allow_local=get_settings().allow_local_mcp,
                )
            )
        except McpDiscoveryError as error:
            raise RuntimeError(error.message) from error
        artifacts: list[McpArtifact] = []
        model_content: list[dict[str, Any]] = []
        for item in result.content:
            if item.get("type") != "image":
                model_content.append(item)
                continue
            encoded = item.get("data")
            mime_type = item.get("mimeType") or item.get("mime_type")
            if not isinstance(encoded, str) or mime_type != "image/png":
                raise RuntimeError("MCP image artifact is invalid")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise RuntimeError("MCP image artifact is invalid") from error
            if len(data) > MAX_ARTIFACT_BYTES:
                raise RuntimeError("MCP image artifact is too large")
            artifacts.append(
                McpArtifact(
                    data=data,
                    mime_type=mime_type,
                    filename="expense-comparison.png",
                )
            )
        return ToolExecutionResult(
            encode_tool_result(
                {
                    "content": model_content,
                    "structured_content": None if artifacts else result.structured_content,
                    "is_error": result.is_error,
                }
            ),
            is_error=result.is_error,
            artifacts=tuple(artifacts),
        )
