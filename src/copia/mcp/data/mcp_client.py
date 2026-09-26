from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

import anyio
import httpcore2
import httpx2
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from copia.mcp.domain.models.mcp_call_result import McpCallResult
from copia.mcp.domain.models.mcp_discovery_result import McpDiscoveryResult
from copia.mcp.domain.models.mcp_server_summary import McpServerSummary
from copia.mcp.domain.models.mcp_tool_summary import McpToolSummary

MAX_ENDPOINT_LENGTH = 2048
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOOLS = 100
MAX_DESCRIPTION_LENGTH = 4000
MAX_PAGES = 20
MAX_ERROR_MESSAGE_LENGTH = 1000
MAX_HEADER_NAME_LENGTH = 256
MAX_HEADER_VALUE_LENGTH = 4096
MAX_ERROR_BODY_BYTES = 8 * 1024
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 10.0
WRITE_TIMEOUT_SECONDS = 5.0
OVERALL_TIMEOUT_SECONDS = 20.0

MCP_ENDPOINT_REJECTED = "mcp_endpoint_rejected"
MCP_TIMEOUT = "mcp_timeout"
MCP_REDIRECT_REJECTED = "mcp_redirect_rejected"
MCP_CONNECTION_FAILED = "mcp_connection_failed"
MCP_RESPONSE_TOO_LARGE = "mcp_response_too_large"
MCP_PROTOCOL_ERROR = "mcp_protocol_error"
MCP_HEADER_REJECTED = "mcp_header_rejected"
MCP_AUTH_REQUIRED = "mcp_auth_required"
MCP_ACCESS_DENIED = "mcp_access_denied"

_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PROTECTED_HEADERS = frozenset(
    {
        "accept",
        "connection",
        "content-length",
        "content-type",
        "cookie",
        "forwarded",
        "host",
        "keep-alive",
        "proxy-connection",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "via",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
    }
)

_METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("168.63.129.16/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)

# The SDK's Streamable HTTP transport logs session IDs and complete SSE messages at INFO/DEBUG.
# Discovery never needs those logs, so keep these implementation loggers silent for this process.
logging.getLogger("mcp.client.streamable_http").disabled = True
logging.getLogger("client").disabled = True


class McpDiscoveryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _ValidatedEndpoint:
    url: str
    hostname: str
    port: int
    address: str


def _find_nested_exception(
    error: BaseException, exception_type: type[BaseException]
) -> BaseException | None:
    if isinstance(error, exception_type):
        return error
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            match = _find_nested_exception(nested, exception_type)
            if match is not None:
                return match
    return None


def _reject(message: str = "MCP endpoint must be a public HTTPS URL") -> McpDiscoveryError:
    return McpDiscoveryError(MCP_ENDPOINT_REJECTED, message)


def _is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if any(address in network for network in _METADATA_NETWORKS):
        return True
    return not address.is_global or any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _is_loopback_hostname(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def _parse_endpoint(endpoint: str, *, allow_local: bool = False) -> SplitResult:
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        raise _reject("MCP endpoint exceeds the allowed length")
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise _reject() from error
    scheme = parsed.scheme.lower()
    local_endpoint = bool(hostname) and allow_local and _is_loopback_hostname(hostname)
    if (
        (scheme != "https" and not (local_endpoint and scheme == "http"))
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "@" in parsed.netloc
        or hostname.endswith(".")
        and hostname == "."
    ):
        raise _reject()
    if "%" in hostname:
        raise _reject()
    if port is None:
        port = 80 if scheme == "http" else 443
    if not 1 <= port <= 65535:
        raise _reject()
    return parsed


def _request_headers(header_name: str | None, header_value: str | None) -> dict[str, str]:
    normalized_name = header_name.strip() if header_name is not None else ""
    normalized_value = header_value.strip() if header_value is not None else ""
    if not normalized_name and not normalized_value:
        return {}
    if not normalized_name or not normalized_value:
        raise McpDiscoveryError(
            MCP_HEADER_REJECTED,
            "MCP header name and value must be provided together",
        )
    if (
        len(normalized_name) > MAX_HEADER_NAME_LENGTH
        or len(normalized_value) > MAX_HEADER_VALUE_LENGTH
        or not _HEADER_NAME_PATTERN.fullmatch(normalized_name)
        or normalized_name.lower() in _PROTECTED_HEADERS
        or not normalized_value.isascii()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized_value)
    ):
        raise McpDiscoveryError(MCP_HEADER_REJECTED, "MCP request header is not allowed")
    return {normalized_name: normalized_value}


async def _validate_endpoint(endpoint: str, *, allow_local: bool = False) -> _ValidatedEndpoint:
    parsed = _parse_endpoint(endpoint, allow_local=allow_local)
    hostname = parsed.hostname
    assert hostname is not None
    port = parsed.port or (80 if parsed.scheme.lower() == "http" else 443)
    try:
        address_info = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
    except (OSError, socket.gaierror, UnicodeError) as error:
        raise _reject("MCP endpoint DNS lookup failed") from error

    addresses: list[str] = []
    for family, _, _, _, sockaddr in address_info:
        raw_address = sockaddr[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise _reject() from error
        local_endpoint = allow_local and _is_loopback_hostname(hostname)
        mapped = getattr(address, "ipv4_mapped", None)
        effective_address = mapped or address
        if local_endpoint and not effective_address.is_loopback:
            raise _reject("Local MCP endpoint must resolve only to loopback addresses")
        if not local_endpoint and _is_blocked_address(address):
            raise _reject("MCP endpoint resolves to a blocked network address")
        if family in (socket.AF_INET, socket.AF_INET6) and raw_address not in addresses:
            addresses.append(raw_address)
    if not addresses:
        raise _reject("MCP endpoint has no public network address")
    return _ValidatedEndpoint(
        url=endpoint,
        hostname=hostname,
        port=port,
        address=addresses[0],
    )


class _PinnedNetworkBackend(httpcore2.AsyncNetworkBackend):
    """Connect to the address validated immediately before creating the client."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._backend = httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        return await self._backend.connect_tcp(
            self._address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self, *args: object, **kwargs: object
    ) -> httpcore2.AsyncNetworkStream:
        raise RuntimeError("Unix sockets are not supported for MCP discovery")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _LimitedResponseStream(httpx2.AsyncByteStream):
    def __init__(self, stream: httpx2.AsyncByteStream) -> None:
        self._stream = stream
        self._total = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            self._total += len(chunk)
            if self._total > MAX_RESPONSE_BYTES:
                raise McpDiscoveryError(
                    MCP_RESPONSE_TOO_LARGE,
                    "MCP response exceeds the allowed size",
                )
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class _LimitedPinnedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, address: str) -> None:
        delegate = httpx2.AsyncHTTPTransport(trust_env=False, retries=0)
        # httpx2 does not expose httpcore's network backend publicly. The SDK's
        # transport is built on this pool, so replace only that backend to pin
        # the already validated DNS result while retaining hostname-based TLS.
        delegate._pool._network_backend = _PinnedNetworkBackend(address)  # type: ignore[attr-defined]
        self._delegate = delegate

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._delegate.handle_async_request(request)
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise McpDiscoveryError(
                MCP_REDIRECT_REJECTED,
                "MCP server redirects are not supported",
            )
        if response.status_code in (401, 403):
            body = await _read_limited_response_body(response)
            await response.aclose()
            if response.status_code == 401:
                raise McpDiscoveryError(
                    MCP_AUTH_REQUIRED,
                    _safe_remote_error_message(body, "MCP server requires authorization"),
                )
            raise McpDiscoveryError(
                MCP_ACCESS_DENIED,
                _safe_remote_error_message(body, "MCP server denied access"),
            )
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    await response.aclose()
                    raise McpDiscoveryError(
                        MCP_RESPONSE_TOO_LARGE,
                        "MCP response exceeds the allowed size",
                    )
            except ValueError:
                raise McpDiscoveryError(
                    MCP_PROTOCOL_ERROR,
                    "MCP server returned an invalid response",
                ) from None
        return httpx2.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_LimitedResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._delegate.aclose()


def _safe_text(value: object | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


async def _read_limited_response_body(response: httpx2.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        remaining = MAX_ERROR_BODY_BYTES - total
        if remaining <= 0:
            break
        bounded_chunk = chunk[:remaining]
        chunks.append(bounded_chunk)
        total += len(bounded_chunk)
        if total >= MAX_ERROR_BODY_BYTES:
            break
    return b"".join(chunks)


def _safe_remote_error_message(body: bytes, fallback: str) -> str:
    message = body.decode("utf-8", errors="replace").strip()
    return message[:MAX_ERROR_MESSAGE_LENGTH] or fallback


def _safe_protocol_message(error: BaseException) -> str:
    """Return the useful protocol diagnostic without exposing arbitrary payloads."""
    nested_mcp_error = _find_nested_exception(error, MCPError)
    if isinstance(nested_mcp_error, MCPError):
        message = nested_mcp_error.message.strip()
    elif isinstance(error, McpDiscoveryError):
        message = error.message.strip()
    else:
        message = " ".join(str(error).split())
    return message[:MAX_ERROR_MESSAGE_LENGTH] or "MCP server returned an invalid protocol response"


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
        raise McpDiscoveryError(MCP_PROTOCOL_ERROR, _safe_protocol_message(error)) from error
