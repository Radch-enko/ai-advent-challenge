import asyncio
import json
from datetime import UTC, datetime

from copia.agents.domain.models.agent_config import AgentConfig
from copia.mcp.application.mcp_tool_resolver import McpToolResolver
from copia.mcp.data.mcp_tool_executor import McpToolExecutor
from copia.mcp.domain.models.mcp_access_config import McpAccessConfig
from copia.mcp.domain.models.mcp_call_result import McpCallResult
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult
from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary
from copia.mcp.domain.services.mcp_tool_loop import ResolvedMcpTool, provider_tool_alias
from copia.providers.domain.models.tool_definition import ToolDefinition


def connection() -> McpConnection:
    return McpConnection(
        id="finances",
        name="Finances",
        endpoint="https://example.test/mcp",
        updated_at=datetime.now(UTC),
    )


def test_resolver_maps_enabled_tool_to_provider_definition() -> None:
    source = connection()

    async def threadpool(action, *args):
        return action(*args)

    async def discover(_connection):
        return McpDiscoveryResult(
            server=McpServerSummary(name="Finances"),
            endpoint=source.endpoint,
            tools=[
                McpToolSummary(
                    name="search",
                    description="Find expenses",
                    input_schema={"type": "object"},
                )
            ],
        )

    resolver = McpToolResolver(
        lambda connection_id: source if connection_id == source.id else None,
        lambda: threadpool,
        lambda: discover,
    )
    config = AgentConfig(
        name="Accountant",
        provider="openai",
        model="model",
        mcp_access=[McpAccessConfig(connection_id=source.id, enabled_tools=["search"])],
    )

    resolved = asyncio.run(resolver.resolve(config))

    assert len(resolved) == 1
    assert resolved[0].alias == provider_tool_alias("finances", "search")
    assert resolved[0].definition.parameters == {"type": "object"}


def test_executor_forwards_tool_request_and_encodes_result() -> None:
    source = connection()
    calls = []

    async def call_tool(endpoint, tool_name, arguments, **options):
        calls.append((endpoint, tool_name, arguments, options))
        return McpCallResult(content=[{"type": "text", "text": "ok"}], is_error=False)

    executor = McpToolExecutor(
        lambda connection_id: source if connection_id == source.id else None,
        lambda _connection: ("Authorization", "test-token"),
        lambda: call_tool,
    )
    tool = ResolvedMcpTool(
        alias="alias",
        connection_id=source.id,
        connection_name=source.name,
        tool_name="search",
        definition=ToolDefinition(name="alias", parameters={"type": "object"}),
    )

    result = executor.execute(tool, {"category": "food"})

    assert calls[0][:3] == (source.endpoint, "search", {"category": "food"})
    assert calls[0][3]["header_name"] == "Authorization"
    assert calls[0][3]["header_value"] == "test-token"
    assert json.loads(result.content)["content"] == [{"type": "text", "text": "ok"}]
    assert result.is_error is False
