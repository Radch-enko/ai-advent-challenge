from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.mcp.api.discovery import DiscoverConnection
from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.domain.models.mcp_connection import McpConnection


def make_test_mcp_connection(
    get_repository: Callable[[], McpConnectionsRepository],
    get_discover_connection: Callable[[], DiscoverConnection],
) -> Callable[[str], Awaitable[McpConnection]]:
    async def test_mcp_connection(connection_id: str) -> McpConnection:
        connection = await run_in_threadpool(get_repository().get, connection_id)
        if connection is None:
            raise HTTPException(
                404,
                detail={"code": "mcp_connection_not_found", "message": "MCP connection not found"},
            )
        discovery = await get_discover_connection()(connection)
        updated = connection.model_copy(
            update={
                "server": discovery.server,
                "tools": discovery.tools,
                "updated_at": datetime.now(UTC),
            }
        )
        return await run_in_threadpool(get_repository().save, updated)

    return test_mcp_connection
