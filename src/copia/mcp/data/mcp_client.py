from __future__ import annotations

from collections.abc import Iterable

import anyio
import httpx2
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from copia.mcp.data.mcp_endpoint import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_DESCRIPTION_LENGTH,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_PAGES,
    MAX_RESPONSE_BYTES,
    MAX_TOOLS,
    MCP_CONNECTION_FAILED,
    MCP_PROTOCOL_ERROR,
    MCP_RESPONSE_TOO_LARGE,
    MCP_TIMEOUT,
    OVERALL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
    McpDiscoveryError,
    _find_nested_exception,
    _request_headers,
    _validate_endpoint,
    _ValidatedEndpoint,
)
from copia.mcp.data.mcp_transport import (
    _LimitedPinnedTransport,
)
from copia.mcp.domain.models.mcp_call_result import McpCallResult
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult
from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary
from copia.security.domain.services.credential_sanitizer import sanitize_text


def _safe_text(value: object | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def _safe_protocol_message(error: BaseException) -> str:
    """Return the useful protocol diagnostic without exposing arbitrary payloads."""
    nested_mcp_error = _find_nested_exception(error, MCPError)
    if isinstance(nested_mcp_error, MCPError):
        message = nested_mcp_error.message.strip()
    elif isinstance(nested := _find_nested_exception(error, McpDiscoveryError), McpDiscoveryError):
        message = nested.message.strip()
    elif isinstance(error, BaseExceptionGroup):
        message = next(
            (str(nested).strip() for nested in _leaf_exceptions(error) if str(nested).strip()),
            "",
        )
    else:
        message = " ".join(str(error).split())
    return (
        sanitize_text(message)[:MAX_ERROR_MESSAGE_LENGTH]
        or "MCP server returned an invalid protocol response"
    )


def _leaf_exceptions(error: BaseException) -> Iterable[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            yield from _leaf_exceptions(nested)
    else:
        yield error


def _tool_summaries(pages: list[types.ListToolsResult]) -> list[McpToolSummary]:
    summaries: list[McpToolSummary] = []
    for page in pages:
        for tool in page.tools:
            if len(summaries) >= MAX_TOOLS:
                raise McpDiscoveryError(
                    MCP_RESPONSE_TOO_LARGE,
                    "MCP server returned too many tools",
                )
            name = _safe_text(tool.name, 200)
            if not name:
                raise McpDiscoveryError(MCP_PROTOCOL_ERROR, "MCP tool has no valid name")
            summaries.append(
                McpToolSummary(
                    name=name,
                    description=_safe_text(tool.description, MAX_DESCRIPTION_LENGTH),
                    input_schema=getattr(tool, "input_schema", {}),
                )
            )
    return summaries


async def _list_tool_pages(client: Client) -> list[types.ListToolsResult]:
    pages: list[types.ListToolsResult] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        page = await client.list_tools(cursor=cursor)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            return pages
    raise McpDiscoveryError(
        MCP_RESPONSE_TOO_LARGE,
        "MCP server returned too many tool pages",
    )


async def _discover(
    validated: _ValidatedEndpoint, request_headers: dict[str, str]
) -> McpDiscoveryResult:
    timeout = httpx2.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=READ_TIMEOUT_SECONDS,
        write=WRITE_TIMEOUT_SECONDS,
        pool=CONNECT_TIMEOUT_SECONDS,
    )
    transport = _LimitedPinnedTransport(validated.address)
    async with httpx2.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        max_redirects=0,
        trust_env=False,
        headers=request_headers,
    ) as http_client:
        mcp_transport = streamable_http_client(
            validated.url,
            http_client=http_client,
            terminate_on_close=True,
        )
        async with Client(
            mcp_transport,
            mode="auto",
            read_timeout_seconds=READ_TIMEOUT_SECONDS,
            cache=None,
        ) as client:
            pages = await _list_tool_pages(client)
            server_info = client.server_info
            return McpDiscoveryResult(
                server=McpServerSummary(
                    name=_safe_text(getattr(server_info, "name", None), 200),
                    version=_safe_text(getattr(server_info, "version", None), 100),
                ),
                endpoint=validated.url,
                tools=_tool_summaries(pages),
            )


async def discover_mcp_tools(
    endpoint: str,
    *,
    header_name: str | None = None,
    header_value: str | None = None,
    allow_local: bool = False,
) -> McpDiscoveryResult:
    try:
        request_headers = _request_headers(header_name, header_value)
        with anyio.fail_after(OVERALL_TIMEOUT_SECONDS):
            validated = await _validate_endpoint(endpoint, allow_local=allow_local)
            return await _discover(validated, request_headers)
    except McpDiscoveryError:
        raise
    except TimeoutError as error:
        raise McpDiscoveryError(
            MCP_TIMEOUT,
            "MCP server did not respond within the allowed time",
        ) from error
    except (httpx2.TimeoutException, anyio.get_cancelled_exc_class()) as error:
        raise McpDiscoveryError(
            MCP_TIMEOUT,
            "MCP server did not respond within the allowed time",
        ) from error
    except (httpx2.HTTPError, OSError, RuntimeError) as error:
        raise McpDiscoveryError(
            MCP_CONNECTION_FAILED,
            "Could not connect to MCP server",
        ) from error
    except MCPError as error:
        raise McpDiscoveryError(
            MCP_PROTOCOL_ERROR,
            _safe_protocol_message(error),
        ) from error
    except Exception as error:
        nested_discovery_error = _find_nested_exception(error, McpDiscoveryError)
        if isinstance(nested_discovery_error, McpDiscoveryError):
            raise nested_discovery_error from error
        if _find_nested_exception(error, MCPError):
            raise McpDiscoveryError(MCP_PROTOCOL_ERROR, _safe_protocol_message(error)) from error
        if _find_nested_exception(error, TimeoutError) or _find_nested_exception(
            error, httpx2.TimeoutException
        ):
            raise McpDiscoveryError(
                MCP_TIMEOUT, "MCP server did not respond within the allowed time"
            ) from error
        if any(
            _find_nested_exception(error, exception_type)
            for exception_type in (httpx2.HTTPError, OSError)
        ):
            raise McpDiscoveryError(
                MCP_CONNECTION_FAILED, "Could not connect to MCP server"
            ) from error
        raise McpDiscoveryError(
            MCP_PROTOCOL_ERROR,
            _safe_protocol_message(error),
        ) from error


async def _call_tool(
    validated: _ValidatedEndpoint,
    request_headers: dict[str, str],
    tool_name: str,
    arguments: dict[str, object],
) -> McpCallResult:
    timeout = httpx2.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=READ_TIMEOUT_SECONDS,
        write=WRITE_TIMEOUT_SECONDS,
        pool=CONNECT_TIMEOUT_SECONDS,
    )
    async with httpx2.AsyncClient(
        transport=_LimitedPinnedTransport(validated.address),
        timeout=timeout,
        follow_redirects=False,
        max_redirects=0,
        trust_env=False,
        headers=request_headers,
    ) as http_client:
        transport = streamable_http_client(
            validated.url,
            http_client=http_client,
            terminate_on_close=True,
        )
        async with Client(
            transport,
            mode="auto",
            read_timeout_seconds=READ_TIMEOUT_SECONDS,
            cache=None,
        ) as client:
            result = await client.call_tool(tool_name, arguments=arguments)
            content = [item.model_dump(mode="json") for item in result.content]
            encoded_size = len(str(content).encode("utf-8"))
            if encoded_size > MAX_RESPONSE_BYTES:
                raise McpDiscoveryError(
                    MCP_RESPONSE_TOO_LARGE,
                    "MCP response exceeds the allowed size",
                )
            return McpCallResult(
                content=content,
                structured_content=(
                    result.structured_content
                    if isinstance(result.structured_content, dict)
                    else None
                ),
                is_error=bool(result.is_error),
            )


async def call_mcp_tool(
    endpoint: str,
    tool_name: str,
    arguments: dict[str, object],
    *,
    header_name: str | None = None,
    header_value: str | None = None,
    allow_local: bool = False,
) -> McpCallResult:
    try:
        request_headers = _request_headers(header_name, header_value)
        with anyio.fail_after(OVERALL_TIMEOUT_SECONDS):
            validated = await _validate_endpoint(endpoint, allow_local=allow_local)
            return await _call_tool(validated, request_headers, tool_name, arguments)
    except McpDiscoveryError:
        raise
    except (TimeoutError, httpx2.TimeoutException, anyio.get_cancelled_exc_class()) as error:
        raise McpDiscoveryError(
            MCP_TIMEOUT,
            "MCP server did not respond within the allowed time",
        ) from error
    except (httpx2.HTTPError, OSError, RuntimeError) as error:
        raise McpDiscoveryError(
            MCP_CONNECTION_FAILED,
            "Could not connect to MCP server",
        ) from error
    except MCPError as error:
        raise McpDiscoveryError(MCP_PROTOCOL_ERROR, _safe_protocol_message(error)) from error
    except Exception as error:
        nested = _find_nested_exception(error, McpDiscoveryError)
        if isinstance(nested, McpDiscoveryError):
            raise nested from error
        if _find_nested_exception(error, MCPError):
            raise McpDiscoveryError(MCP_PROTOCOL_ERROR, _safe_protocol_message(error)) from error
        if _find_nested_exception(error, TimeoutError) or _find_nested_exception(
            error, httpx2.TimeoutException
        ):
            raise McpDiscoveryError(
                MCP_TIMEOUT, "MCP server did not respond within the allowed time"
            ) from error
        if any(
            _find_nested_exception(error, exception_type)
            for exception_type in (httpx2.HTTPError, OSError)
        ):
            raise McpDiscoveryError(
                MCP_CONNECTION_FAILED, "Could not connect to MCP server"
            ) from error
        raise McpDiscoveryError(MCP_PROTOCOL_ERROR, _safe_protocol_message(error)) from error
