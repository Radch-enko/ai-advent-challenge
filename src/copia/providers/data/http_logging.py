from __future__ import annotations

from typing import Any

import httpx

from copia.security.domain.services.credential_sanitizer import sanitize_url


def record_response(response: httpx.Response) -> None:
    """Export a completed provider request and response as one structured log."""
    request = response.request
    from copia.common.observability import (
        _structured_body_value,
        emit_http_exchange,
        http_body_capture_enabled,
    )

    request_body = response_body = None
    request_truncated = response_truncated = False
    if http_body_capture_enabled():
        request_body, request_truncated = _request_body(request)
        response_body, response_truncated = _structured_body_value(
            response.headers.get("content-type", ""), response.content
        )
    emit_http_exchange(
        direction="outbound",
        method=request.method,
        url=sanitize_url(str(request.url)),
        request_headers=request.headers,
        request_body=request_body,
        request_body_truncated=request_truncated,
        status_code=response.status_code,
        response_headers=response.headers,
        response_body=response_body,
        response_body_truncated=response_truncated,
        context=request.extensions.get("copia.otel.span_context"),
    )


def record_stream_response(
    response: httpx.Response,
    *,
    response_body: object | None = None,
    stream_events: list[dict[str, Any]] | None = None,
    stream_events_truncated: bool = False,
) -> None:
    """Export a completed provider stream, including its parsed SSE data frames."""
    request = response.request
    from copia.common.observability import (
        _structured_body_value,
        emit_http_exchange,
        http_body_capture_enabled,
    )

    request_body = None
    request_truncated = False
    captured_response: object | None = None
    response_truncated = False
    if http_body_capture_enabled():
        request_body, request_truncated = _request_body(request)
        if response.is_error and response_body is None and not stream_events:
            captured_response, response_truncated = _structured_body_value(
                response.headers.get("content-type", ""), response.content
            )
        elif stream_events is not None:
            captured_response = {
                "events": stream_events,
                "final": response_body,
                "completed": response_body is not None,
            }
            captured_response, response_truncated = _structured_body_value(
                "application/json",
                captured_response,
                overflow=stream_events_truncated,
            )
        elif response_body is not None:
            captured_response, response_truncated = _structured_body_value(
                "application/json", response_body
            )
    emit_http_exchange(
        direction="outbound",
        method=request.method,
        url=sanitize_url(str(request.url)),
        request_headers=request.headers,
        request_body=request_body,
        request_body_truncated=request_truncated,
        status_code=response.status_code,
        response_headers=response.headers,
        response_body=captured_response,
        response_body_truncated=response_truncated,
        context=request.extensions.get("copia.otel.span_context"),
    )


def _request_body(request: httpx.Request) -> tuple[object | None, bool]:
    from copia.common.observability import _structured_body_value

    explicit_body = request.extensions.get("copia.otel.request.body")
    if explicit_body is not None:
        return _structured_body_value("application/json", explicit_body)
    try:
        return _structured_body_value(request.headers.get("content-type", ""), request.content)
    except httpx.RequestNotRead:
        return None, True
