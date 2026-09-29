from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from copia.common.configuration import get_settings

MAX_ENDPOINT_LENGTH = 2048
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOOLS = 100
MAX_DESCRIPTION_LENGTH = 4000
MAX_PAGES = 20
MAX_ERROR_MESSAGE_LENGTH = 1000
MAX_HEADER_NAME_LENGTH = 256
MAX_HEADER_VALUE_LENGTH = 4096
MAX_ERROR_BODY_BYTES = 8 * 1024
TRUSTED_DOCKER_MCP_ENDPOINT = "http://mcp-server:8001/mcp"
CONNECT_TIMEOUT_SECONDS = 15.0
READ_TIMEOUT_SECONDS = 40.0
WRITE_TIMEOUT_SECONDS = 5.0
OVERALL_TIMEOUT_SECONDS = 40.0

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


def _parse_endpoint(
    endpoint: str, *, allow_local: bool = False, allow_trusted_docker: bool = False
) -> SplitResult:
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        raise _reject("MCP endpoint exceeds the allowed length")
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise _reject() from error
    scheme = parsed.scheme.lower()
    local_endpoint = bool(hostname and allow_local and _is_loopback_hostname(hostname))
    docker_endpoint = allow_trusted_docker and hostname == "mcp-server" and port == 8001
    if (
        (scheme != "https" and not ((local_endpoint or docker_endpoint) and scheme == "http"))
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
    trusted_docker_endpoint = (
        endpoint == TRUSTED_DOCKER_MCP_ENDPOINT
        and get_settings().trusted_mcp_endpoint == TRUSTED_DOCKER_MCP_ENDPOINT
    )
    parsed = _parse_endpoint(
        endpoint,
        allow_local=allow_local,
        allow_trusted_docker=trusted_docker_endpoint,
    )
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
        if not isinstance(raw_address, str):
            raise _reject("MCP endpoint DNS lookup returned an invalid address")
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise _reject() from error
        local_endpoint = allow_local and _is_loopback_hostname(hostname)
        mapped = getattr(address, "ipv4_mapped", None)
        effective_address = mapped or address
        docker_private_endpoint = trusted_docker_endpoint and hostname == "mcp-server"
        if local_endpoint and not effective_address.is_loopback:
            raise _reject("Local MCP endpoint must resolve only to loopback addresses")
        if docker_private_endpoint and (
            effective_address.version != 4
            or not effective_address.is_private
            or effective_address.is_link_local
            or effective_address.is_loopback
            or any(effective_address in network for network in _METADATA_NETWORKS)
        ):
            raise _reject("Trusted Docker MCP endpoint must resolve to a private address")
        if not local_endpoint and not docker_private_endpoint and _is_blocked_address(address):
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
