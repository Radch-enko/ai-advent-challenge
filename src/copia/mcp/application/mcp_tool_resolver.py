from collections.abc import Awaitable, Callable
from typing import Any

from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, provider_tool_alias
from copia.providers.domain.models.tool_definition import ToolDefinition


class McpToolResolver:
    def __init__(
        self,
        get_connection: Callable[[str], McpConnection | None],
        get_threadpool: Callable[[], Callable[..., Awaitable[Any]]],
        get_discover_connection: Callable[
            [], Callable[[McpConnection], Awaitable[McpDiscoveryResult]]
        ],
    ) -> None:
        self._get_connection = get_connection
        self._get_threadpool = get_threadpool
        self._get_discover_connection = get_discover_connection

    async def resolve(self, config: AgentConfig) -> list[ResolvedMcpTool]:
        resolved: list[ResolvedMcpTool] = []
        for access in config.mcp_access:
            connection = await self._get_threadpool()(self._get_connection, access.connection_id)
            if connection is None:
                raise RuntimeError(f"MCP connection {access.connection_id} is unavailable")
            discovery = await self._get_discover_connection()(connection)
            discovered = {tool.name: tool for tool in discovery.tools}
            for tool_name in access.enabled_tools:
                tool = discovered.get(tool_name)
                if tool is None:
                    raise RuntimeError(
                        f"MCP tool {tool_name} is unavailable on connection {connection.name}"
                    )
                alias = provider_tool_alias(connection.id, tool.name)
                resolved.append(
                    ResolvedMcpTool(
                        alias=alias,
                        connection_id=connection.id,
                        connection_name=connection.name,
                        tool_name=tool.name,
                        definition=ToolDefinition(
                            name=alias,
                            description=tool.description,
                            parameters=tool.input_schema,
                        ),
                    )
                )
        return resolved
