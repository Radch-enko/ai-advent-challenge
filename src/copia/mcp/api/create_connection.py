from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.mcp.api.discovery import DiscoverConnection
from copia.mcp.data.mcp_connection_conflict_error import McpConnectionConflictError
from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.data.mcp_connections_storage_error import McpConnectionsStorageError
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_connection_input import McpConnectionInput


def make_create_mcp_connection(
    get_repository: Callable[[], McpConnectionsRepository],
    get_discover_connection: Callable[[], DiscoverConnection],
) -> Callable[[McpConnectionInput], Awaitable[McpConnection]]:
    async def create_mcp_connection(request: McpConnectionInput) -> McpConnection:
        discovery = await get_discover_connection()(request)
        connection = McpConnection(
            **request.model_dump(),
            server=discovery.server,
            tools=discovery.tools,
            updated_at=datetime.now(UTC),
        )
        try:
            return await run_in_threadpool(get_repository().create, connection)
        except McpConnectionConflictError as error:
            raise HTTPException(
                409, detail={"code": "mcp_connection_exists", "message": str(error)}
            ) from error
        except McpConnectionsStorageError as error:
            raise HTTPException(
                500, detail={"code": "mcp_storage_error", "message": str(error)}
            ) from error

    return create_mcp_connection
