from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.data.mcp_connections_storage_error import McpConnectionsStorageError


def make_delete_mcp_connection(
    get_repository: Callable[[], McpConnectionsRepository],
    is_connection_used: Callable[[str], bool],
) -> Callable[[str], Awaitable[None]]:
    async def delete_mcp_connection(connection_id: str) -> None:
        try:
            if await run_in_threadpool(is_connection_used, connection_id):
                raise HTTPException(
                    409,
                    detail={
                        "code": "mcp_connection_in_use",
                        "message": "MCP connection is used by an agent",
                    },
                )
            if not await run_in_threadpool(get_repository().delete, connection_id):
                raise HTTPException(
                    404,
                    detail={
                        "code": "mcp_connection_not_found",
                        "message": "MCP connection not found",
                    },
                )
        except McpConnectionsStorageError as error:
            raise HTTPException(
                500, detail={"code": "mcp_storage_error", "message": str(error)}
            ) from error

    return delete_mcp_connection
