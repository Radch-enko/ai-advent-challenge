import os
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from copia.mcp.api.errors import MCP_ERROR_STATUS_CODES
from copia.mcp.api.models.mcp_discovery_request import McpDiscoveryRequest
from copia.mcp.data.mcp_client import McpDiscoveryError
from copia.mcp.domain.models.mcp_connection import McpConnection
from copia.mcp.domain.models.mcp_connection_input import McpConnectionInput
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult

DiscoverMcpTools = Callable[..., Awaitable[McpDiscoveryResult]]
DiscoverConnection = Callable[[McpConnection | McpConnectionInput], Awaitable[McpDiscoveryResult]]


def mcp_header(connection: McpConnection | McpConnectionInput) -> tuple[str | None, str | None]:
    if connection.header_value_env is None:
        return None, None
    value = os.getenv(connection.header_value_env)
    if value is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "mcp_secret_unavailable",
                "message": f"Environment variable {connection.header_value_env} is not configured",
            },
        )
    return connection.header_name, value


def make_discover_connection(get_discoverer: Callable[[], DiscoverMcpTools]) -> DiscoverConnection:
    async def discover_connection(
        connection: McpConnection | McpConnectionInput,
    ) -> McpDiscoveryResult:
        header_name, header_value = mcp_header(connection)
        try:
            return await get_discoverer()(
                connection.endpoint,
                header_name=header_name,
                header_value=header_value,
                allow_local=os.getenv("COPIA_ALLOW_LOCAL_MCP", "true").lower() != "false",
            )
        except McpDiscoveryError as error:
            raise HTTPException(
                status_code=MCP_ERROR_STATUS_CODES.get(error.code, 502),
                detail={"code": error.code, "message": error.message},
            ) from error

    return discover_connection


def make_discover_mcp(
    get_discoverer: Callable[[], DiscoverMcpTools],
) -> Callable[[McpDiscoveryRequest], Awaitable[McpDiscoveryResult]]:
    async def discover_mcp(request: McpDiscoveryRequest) -> McpDiscoveryResult:
        try:
            allow_local = os.getenv("COPIA_ALLOW_LOCAL_MCP", "true").lower() != "false"
            discoverer = get_discoverer()
            if request.header_name is None and request.header_value is None:
                if allow_local:
                    return await discoverer(request.endpoint)
                return await discoverer(request.endpoint, allow_local=False)
            if allow_local:
                return await discoverer(
                    request.endpoint,
                    header_name=request.header_name,
                    header_value=request.header_value,
                )
            return await discoverer(
                request.endpoint,
                header_name=request.header_name,
                header_value=request.header_value,
                allow_local=False,
            )
        except McpDiscoveryError as error:
            raise HTTPException(
                status_code=MCP_ERROR_STATUS_CODES.get(error.code, status.HTTP_502_BAD_GATEWAY),
                detail={"code": error.code, "message": error.message},
            ) from error

    return discover_mcp
