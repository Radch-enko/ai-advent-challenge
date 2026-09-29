from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import cast

import httpcore2
import httpx2
from opentelemetry import trace

from copia.common.observability import (
    MAX_BODY_BYTES,
    _body_value,
    _safe_headers,
    emit_http_log,
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
        self._request = request
        self._response = response
        self._span_context = span_context

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            self._total += len(chunk)
            if self._total > MAX_RESPONSE_BYTES:
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
        body, body_truncated = (
            (None, self._capture_overflow)
            if self._capture_overflow
            else (None, False)
            if self._capture_disabled
            else _body_value(self._response.headers.get("content-type", ""), bytes(self._captured))
        )
        attributes: dict[str, object] = {
            "http.request.method": self._request.method,
            "url.full": sanitize_url(str(self._request.url)),
            "http.request.headers.safe": _safe_headers(self._request.headers),
            "http.response.status_code": self._response.status_code,
            "http.response.headers.safe": _safe_headers(self._response.headers),
            "http.response.body_captured": body is not None,
            "http.body.truncated": body_truncated,
        }
        if body is not None:
            attributes["http.response.body"] = body
        if not self._capture_disabled:
            request_body, request_truncated = _body_value(
                self._request.headers.get("content-type", ""), self._request.content
            )
            attributes["http.body.truncated"] = body_truncated or request_truncated
            if request_body is not None:
                attributes["http.request.body"] = request_body
        emit_http_log("http.mcp.response.complete", attributes, context=self._span_context)

    async def aclose(self) -> None:
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
            request_attributes: dict[str, object] = {
                "http.request.method": getattr(request, "method", ""),
                "url.full": sanitize_url(str(getattr(request, "url", ""))),
                "http.request.headers.safe": (
                    _safe_headers(dict(request.headers.items()))
                    if hasattr(request, "headers")
                    else "{}"
                ),
            }
            try:
                try:
                    body_value, truncated = (
                        _body_value(request.headers.get("content-type", ""), request.content)
                        if http_body_capture_enabled()
                        else (None, False)
                    )
                    if body_value is not None:
                        request_attributes["http.request.body"] = body_value
                    request_attributes["http.body.truncated"] = truncated
                except (AttributeError, RuntimeError):
                    pass
                if hasattr(request, "method") and hasattr(request, "url"):
                    emit_http_log("http.mcp.request", request_attributes, context=span_context)
                response = await self._delegate.handle_async_request(request)
                span.set_attribute("http.response.status_code", response.status_code)
                emit_http_log(
                    "http.mcp.response",
                    {
                        "http.request.method": getattr(request, "method", ""),
                        "url.full": sanitize_url(str(getattr(request, "url", ""))),
                        "http.response.status_code": response.status_code,
                        "http.response.headers.safe": _safe_headers(response.headers),
                        "http.response.body_captured": False,
                    },
                    context=span_context,
                )
            except Exception as error:
                span.set_attribute("error.type", type(error).__name__)
                raise
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise McpDiscoveryError(
                MCP_REDIRECT_REJECTED,
                "MCP server redirects are not supported",
            )
        if response.status_code in (401, 403):
            body = await _read_limited_response_body(response)
            captured_body, truncated = (
                _body_value(response.headers.get("content-type", ""), body)
                if http_body_capture_enabled()
                else (None, False)
            )
            attributes: dict[str, object] = {
                "http.request.method": getattr(request, "method", ""),
                "url.full": sanitize_url(str(getattr(request, "url", ""))),
                "http.request.headers.safe": (
                    _safe_headers(request.headers) if hasattr(request, "headers") else "{}"
                ),
                "http.response.status_code": response.status_code,
                "http.response.headers.safe": _safe_headers(response.headers),
                "http.body.truncated": truncated,
            }
            if captured_body is not None:
                attributes["http.response.body"] = captured_body
            emit_http_log("http.mcp.response.complete", attributes, context=span_context)
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
