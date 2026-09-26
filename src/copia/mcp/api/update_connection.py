from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.mcp.api.discovery import DiscoverConnection
from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.data.mcp_connections_storage_error import McpConnectionsStorageError
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_connection_input import McpConnectionInput


def make_update_mcp_connection(
    get_repository: Callable[[], McpConnectionsRepository],
    get_discover_connection: Callable[[], DiscoverConnection],
) -> Callable[[str, McpConnectionInput], Awaitable[McpConnection]]:
    async def update_mcp_connection(
        connection_id: str, request: McpConnectionInput
    ) -> McpConnection:
        if connection_id != request.id:
            raise HTTPException(
                422,
                detail={"code": "mcp_id_mismatch", "message": "Connection ID cannot be changed"},
            )
        if await run_in_threadpool(get_repository().get, connection_id) is None:
            raise HTTPException(
                404,
                detail={"code": "mcp_connection_not_found", "message": "MCP connection not found"},
            )
        discovery = await get_discover_connection()(request)
        connection = McpConnection(
            **request.model_dump(),
            server=discovery.server,
            tools=discovery.tools,
            updated_at=datetime.now(UTC),
        )
        try:
            return await run_in_threadpool(get_repository().save, connection)
        except McpConnectionsStorageError as error:
            raise HTTPException(
                500, detail={"code": "mcp_storage_error", "message": str(error)}
            ) from error

    return update_mcp_connection
