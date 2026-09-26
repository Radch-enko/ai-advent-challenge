from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.data.mcp_connections_storage_error import McpConnectionsStorageError
from copia.mcp.domain.models.mcp_connection import McpConnection


def make_list_mcp_connections(
    get_repository: Callable[[], McpConnectionsRepository],
) -> Callable[[], Awaitable[list[McpConnection]]]:
    async def list_mcp_connections() -> list[McpConnection]:
        try:
            return await run_in_threadpool(get_repository().list)
        except McpConnectionsStorageError as error:
            raise HTTPException(
                500, detail={"code": "mcp_storage_error", "message": str(error)}
            ) from error

    return list_mcp_connections
