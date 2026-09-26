from collections.abc import Callable

from fastapi import APIRouter

from copia.mcp.api.create_connection import make_create_mcp_connection
from copia.mcp.api.delete_connection import make_delete_mcp_connection
from copia.mcp.api.discovery import DiscoverConnection, DiscoverMcpTools, make_discover_mcp
from copia.mcp.api.list_connections import make_list_mcp_connections
from copia.mcp.api.test_connection import make_test_mcp_connection
from copia.mcp.api.update_connection import make_update_mcp_connection
from copia.mcp.data.mcp_connections_repository import McpConnectionsRepository
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult


def create_mcp_router(
    get_repository: Callable[[], McpConnectionsRepository],
    get_discoverer: Callable[[], DiscoverMcpTools],
    get_discover_connection: Callable[[], DiscoverConnection],
    is_connection_used: Callable[[str], bool],
) -> APIRouter:
    router = APIRouter()
    router.add_api_route(
        "/mcp/discover",
        make_discover_mcp(get_discoverer),
        methods=["POST"],
        response_model=McpDiscoveryResult,
        response_model_exclude_defaults=True,
    )
    router.add_api_route(
        "/mcp/connections",
        make_list_mcp_connections(get_repository),
        methods=["GET"],
        response_model=list[McpConnection],
    )
    router.add_api_route(
        "/mcp/connections",
        make_create_mcp_connection(get_repository, get_discover_connection),
        methods=["POST"],
        response_model=McpConnection,
        status_code=201,
    )
    router.add_api_route(
        "/mcp/connections/{connection_id}",
        make_update_mcp_connection(get_repository, get_discover_connection),
        methods=["PUT"],
        response_model=McpConnection,
    )
    router.add_api_route(
        "/mcp/connections/{connection_id}/test",
        make_test_mcp_connection(get_repository, get_discover_connection),
        methods=["POST"],
        response_model=McpConnection,
    )
    router.add_api_route(
        "/mcp/connections/{connection_id}",
        make_delete_mcp_connection(get_repository, is_connection_used),
        methods=["DELETE"],
        status_code=204,
    )
    return router
