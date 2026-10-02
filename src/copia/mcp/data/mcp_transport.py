from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import cast

import httpcore2
import httpx2
from opentelemetry import trace

from copia.common.observability import (
    MAX_BODY_BYTES,
    _safe_headers,
    _structured_body_value,
    emit_http_exchange,
    http_body_capture_enabled,
)
from copia.mcp.data.mcp_endpoint import (
    MAX_ERROR_BODY_BYTES,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_RESPONSE_BYTES,
    MCP_ACCESS_DENIED,
    MCP_AUTH_REQUIRED,
    MCP_PROTOCOL_ERROR,
    MCP_REDIRECT_REJECTED,
    MCP_RESPONSE_TOO_LARGE,
    McpDiscoveryError,
)
from copia.security.domain.services.credential_sanitizer import sanitize_url


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
    def __init__(
        self,
        stream: httpx2.AsyncByteStream,
        *,
        request: httpx2.Request,
        response: httpx2.Response,
        span_context: object,
    ) -> None:
        self._stream = stream
        self._total = 0
        self._captured = bytearray()
        self._capture_overflow = False
        self._capture_disabled = not http_body_capture_enabled()
        self._log_emitted = False
        self._request = request
        self._response = response
        self._span_context = span_context

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            self._total += len(chunk)
            if self._total > MAX_RESPONSE_BYTES:
                self._capture_overflow = not self._capture_disabled
                self._captured.clear()
                self._emit_response_log()
                raise McpDiscoveryError(
                    MCP_RESPONSE_TOO_LARGE,
                    "MCP response exceeds the allowed size",
                )
            if self._capture_disabled:
                pass
            elif len(self._captured) + len(chunk) > MAX_BODY_BYTES:
                self._capture_overflow = True
                self._captured.clear()
            elif not self._capture_overflow:
                self._captured.extend(chunk)
            yield chunk
        self._emit_response_log()

    def _emit_response_log(self) -> None:
        if self._log_emitted:
            return
        self._log_emitted = True
        response_bytes = None if self._capture_overflow else bytes(self._captured)
        _emit_mcp_exchange(
            self._request,
            self._response,
            self._span_context,
            response_body=response_bytes,
            response_body_truncated=self._capture_overflow,
        )

    async def aclose(self) -> None:
        if not self._log_emitted:
            self._capture_overflow = not self._capture_disabled
            self._captured.clear()
            self._emit_response_log()
        await self._stream.aclose()


class _LimitedPinnedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, address: str) -> None:
        delegate = httpx2.AsyncHTTPTransport(trust_env=False, retries=0)
        # httpx2 does not expose httpcore's network backend publicly. The SDK's
        # transport is built on this pool, so replace only that backend to pin
        # the already validated DNS result while retaining hostname-based TLS.
        delegate._pool._network_backend = _PinnedNetworkBackend(address)
        self._delegate = delegate

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("mcp.http") as span:
            span_context = trace.set_span_in_context(span)
            if hasattr(request, "method"):
                span.set_attribute("http.request.method", request.method)
            if hasattr(request, "url"):
                span.set_attribute("url.full", sanitize_url(str(request.url)))
            if hasattr(request, "headers"):
                safe_headers = _safe_headers(dict(request.headers.items()))
                span.set_attribute("http.request.headers.safe", safe_headers)
            try:
                response = await self._delegate.handle_async_request(request)
                span.set_attribute("http.response.status_code", response.status_code)
            except Exception as error:
                span.set_attribute("error.type", type(error).__name__)
                raise
        if 300 <= response.status_code < 400:
            await response.aclose()
            _emit_mcp_exchange(
                request,
                response,
                span_context,
                response_body_truncated=True,
            )
            raise McpDiscoveryError(
                MCP_REDIRECT_REJECTED,
                "MCP server redirects are not supported",
            )
        if response.status_code in (401, 403):
            body = await _read_limited_response_body(response)
            _emit_mcp_exchange(
                request,
                response,
                span_context,
                response_body=(body if len(body) < MAX_ERROR_BODY_BYTES else None),
                response_body_truncated=len(body) >= MAX_ERROR_BODY_BYTES,
            )
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
                    _emit_mcp_exchange(
                        request,
                        response,
                        span_context,
                        response_body_truncated=True,
                    )
                    raise McpDiscoveryError(
                        MCP_RESPONSE_TOO_LARGE,
                        "MCP response exceeds the allowed size",
                    )
            except ValueError:
                await response.aclose()
                _emit_mcp_exchange(
                    request,
                    response,
                    span_context,
                    response_body_truncated=True,
                )
                raise McpDiscoveryError(
                    MCP_PROTOCOL_ERROR,
                    "MCP server returned an invalid response",
                ) from None
        return httpx2.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_LimitedResponseStream(
                cast(httpx2.AsyncByteStream, response.stream),
                request=request,
                response=response,
                span_context=span_context,
            ),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._delegate.aclose()


def _emit_mcp_exchange(
    request: httpx2.Request,
    response: httpx2.Response,
    span_context: object,
    *,
    response_body: bytes | None = None,
    response_body_truncated: bool = False,
) -> None:
    request_body = response_value = None
    request_body_truncated = False
    if http_body_capture_enabled():
        try:
            request_body, request_body_truncated = _structured_body_value(
                request.headers.get("content-type", ""), request.content
            )
        except (AttributeError, RuntimeError):
            request_body_truncated = True
        if response_body is not None:
            response_value, response_body_truncated = _structured_body_value(
                response.headers.get("content-type", ""), response_body
            )
    emit_http_exchange(
        direction="outbound",
        method=request.method,
        url=sanitize_url(str(request.url)),
        request_headers=request.headers,
        request_body=request_body,
        request_body_truncated=request_body_truncated,
        status_code=response.status_code,
        response_headers=response.headers,
        response_body=response_value,
        response_body_truncated=response_body_truncated,
        context=span_context,
    )


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
