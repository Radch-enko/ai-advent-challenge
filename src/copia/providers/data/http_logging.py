from __future__ import annotations

import httpx

from copia.security.domain.services.credential_sanitizer import sanitize_url


def record_response(response: httpx.Response) -> None:
    """Export a completed provider exchange to SigNoz after its body is consumed."""
    _emit_sig_noz_response(response.request, response)


def _emit_sig_noz_response(request: httpx.Request, response: httpx.Response) -> None:
    """Emit the normalized request/response event consumed by the SigNoz exporter."""
    from copia.common.observability import (
        _body_value,
        _safe_headers,
        emit_http_log,
        http_body_capture_enabled,
    )

    response_body = request_body = None
    truncated = request_truncated = False
    if http_body_capture_enabled():
        response_body, truncated = _body_value(
            response.headers.get("content-type", ""), response.content
        )
        try:
            request_body, request_truncated = _body_value(
                request.headers.get("content-type", ""), request.content
            )
        except httpx.RequestNotRead:
            request_truncated = True
    attributes: dict[str, object] = {
        "http.request.method": request.method,
        "url.full": sanitize_url(str(request.url)),
        "http.request.headers.safe": _safe_headers(request.headers),
        "http.response.status_code": response.status_code,
        "http.response.headers.safe": _safe_headers(response.headers),
        "http.body.truncated": truncated or request_truncated,
    }
    if response_body is not None:
        attributes["http.response.body"] = response_body
    if request_body is not None:
        attributes["http.request.body"] = request_body
    emit_http_log(
        "http.client.response.complete",
        attributes,
        context=request.extensions.get("copia.otel.span_context"),
    )
