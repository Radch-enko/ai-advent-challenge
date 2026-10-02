from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Any, cast

from fastapi import FastAPI
from opentelemetry import trace

from copia.common.configuration import get_settings
from copia.security.domain.services.credential_sanitizer import (
    is_sensitive_key,
    sanitize_text,
    sanitize_url,
    sanitize_value,
)

MAX_BODY_BYTES = 1024 * 1024  # Bounded capture limit per HTTP body.
_provider: Any | None = None
_logger_provider: Any | None = None
_otel_logger: Any | None = None
_http_log_context: ContextVar[dict[str, str] | None] = ContextVar(
    "copia_http_log_context", default=None
)


def _current_http_log_context() -> dict[str, str]:
    return _http_log_context.get() or {}


def _safe_headers(headers: Any) -> str:
    """Compatibility helper for existing span attributes."""
    return json.dumps(_safe_headers_map(headers), ensure_ascii=True)


def _safe_headers_map(headers: Any) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else headers
    safe: dict[str, str] = {}
    for raw_key, raw_value in items:
        key = raw_key.decode("latin-1") if isinstance(raw_key, bytes) else str(raw_key)
        value = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else str(raw_value)
        safe_value = "[REDACTED]" if is_sensitive_key(key) else sanitize_text(value)
        safe[key] = f"{safe[key]}, {safe_value}" if key in safe else safe_value
    return safe


def _http_method_value(method: Any) -> str:
    if isinstance(method, bytes):
        return method.decode("ascii", errors="replace")
    return str(method)


def _body_value(content_type: str, body: bytes) -> tuple[str | None, bool]:
    if not body or not ("json" in content_type.lower() or "text/" in content_type.lower()):
        return None, False
    if len(body) > MAX_BODY_BYTES:
        return None, True
    try:
        text = body.decode("utf-8")
        if "json" in content_type.lower():
            text = json.dumps(sanitize_value(json.loads(text)), ensure_ascii=True)
        else:
            text = sanitize_text(text)
        return text, False
    except (UnicodeDecodeError, ValueError, TypeError):
        return None, False


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    fields: dict[str, str] = {}
    data_lines: list[str] = []

    def append_event() -> None:
        if not fields and not data_lines:
            return
        event: dict[str, Any] = {}
        for name in ("id", "event", "retry"):
            if name in fields:
                event[name] = fields[name]
        if data_lines:
            data = "\n".join(data_lines)
            try:
                event["data"] = json.loads(data)
            except json.JSONDecodeError:
                event["data"] = sanitize_text(data)
        events.append(event)
        fields.clear()
        data_lines.clear()

    for line in text.splitlines():
        if not line:
            append_event()
            continue
        if line.startswith(":"):
            continue
        name, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if name == "data":
            data_lines.append(value)
        elif name in {"id", "event", "retry"}:
            fields[name] = value
    append_event()
    return events


def _structured_body_value(
    content_type: str, body: Any, *, overflow: bool = False
) -> tuple[Any | None, bool]:
    if overflow:
        return None, True
    if body is None or body == b"":
        return None, False
    media_type = content_type.lower()
    if isinstance(body, (dict, list)):
        value = sanitize_value(body)
    else:
        if isinstance(body, bytes):
            if len(body) > MAX_BODY_BYTES:
                return None, True
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                return None, False
        elif isinstance(body, str):
            text = body
        else:
            return None, False
        if "text/event-stream" in media_type:
            value = sanitize_value({"events": _parse_sse_events(text)})
        elif "json" in media_type:
            try:
                value = sanitize_value(json.loads(text))
            except (json.JSONDecodeError, TypeError):
                return None, False
        elif "text/" in media_type:
            value = sanitize_text(text)
        else:
            return None, False
    try:
        encoded = json.dumps(value, ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError):
        return None, False
    if len(encoded) > MAX_BODY_BYTES:
        return None, True
    return value, False


@contextmanager
def bind_http_log_context(
    *, conversation_id: str | None = None, request_id: str | None = None
) -> Iterator[None]:
    current = _current_http_log_context()
    updates = {
        key: value
        for key, value in {
            "conversation_id": conversation_id,
            "request_id": request_id,
        }.items()
        if value is not None
    }
    token = _http_log_context.set({**current, **updates})
    try:
        yield
    finally:
        _http_log_context.reset(token)


def _http_url(scope: dict[str, Any]) -> str:
    headers = dict(scope.get("headers", []))
    host = headers.get(b"host", b"").decode("latin-1")
    if not host:
        server = scope.get("server")
        if server:
            host = str(server[0])
            if len(server) > 1 and server[1] is not None:
                host = f"{host}:{server[1]}"
        else:
            host = "localhost"
    path = scope.get("path", "")
    query = scope.get("query_string", b"").decode("latin-1")
    url = f"{scope.get('scheme', 'http')}://{host}{path}"
    if query:
        url = f"{url}?{query}"
    return sanitize_url(url)


def _request_context_ids(request_value: Any) -> dict[str, str]:
    context = dict(_current_http_log_context())
    if isinstance(request_value, dict):
        for key in ("conversation_id", "request_id"):
            value = request_value.get(key)
            if isinstance(value, str) and value:
                context.setdefault(key, value)
    return context


def emit_http_exchange(
    *,
    direction: str,
    method: Any,
    url: str,
    request_headers: Any,
    request_body: Any = None,
    request_body_truncated: bool = False,
    status_code: int | None = None,
    response_headers: Any = None,
    response_body: Any = None,
    response_body_truncated: bool = False,
    context: Any | None = None,
    request_context: dict[str, str] | None = None,
) -> None:
    """Emit one structured log record for a completed HTTP exchange."""
    exchange_id = str(uuid.uuid4())
    ids = {**_current_http_log_context(), **(request_context or {})}
    request = {
        "method": _http_method_value(method),
        "url": sanitize_url(url),
        "headers": _safe_headers_map(request_headers),
        "body": sanitize_value(request_body),
        "body_truncated": request_body_truncated,
    }
    response: dict[str, Any] = {
        "status_code": status_code,
        "url": sanitize_url(url),
        "headers": _safe_headers_map(response_headers or {}),
        "body": sanitize_value(response_body),
        "body_truncated": response_body_truncated,
    }
    body: dict[str, Any] = {
        "event": "http.exchange",
        "exchange_id": exchange_id,
        "direction": direction,
        "request": request,
        "response": response,
    }
    body.update(ids)
    attributes: dict[str, Any] = {
        "event.name": "http.exchange",
        "exchange_id": exchange_id,
        "http.direction": direction,
        "http.request.method": request["method"],
        "url.full": request["url"],
        "http.response.status_code": status_code or 0,
        "http.request.body_truncated": request_body_truncated,
        "http.response.body_truncated": response_body_truncated,
    }
    attributes.update(ids)
    emit_http_log("http.exchange", attributes, context=context, body=body)


def _safe_attributes(attributes: Any) -> dict[str, Any]:
    if not attributes:
        return {}
    return {
        key: "[REDACTED]"
        if is_sensitive_key(key)
        else sanitize_value(value)
        if isinstance(value, (dict, list))
        else sanitize_text(value)
        if isinstance(value, str)
        else value
        for key, value in attributes.items()
    }


def _safe_spans(spans: Any) -> list[Any]:
    class SanitizedSpan:
        def __init__(self, span: Any) -> None:
            self._span = span
            self.attributes = _safe_attributes(span.attributes)
            self.events = tuple(
                replace(event, attributes=_safe_attributes(event.attributes))
                for event in span.events
            )
            self.status = span.status
            if self.status.description:
                self.status = replace(
                    self.status, description=sanitize_text(self.status.description)
                )

        def __getattr__(self, name: str) -> Any:
            return getattr(self._span, name)

    safe = []
    for span in spans:
        safe.append(SanitizedSpan(span))
    return safe


def emit_http_log(
    event_name: str,
    attributes: dict[str, Any],
    *,
    context: Any | None = None,
    body: Any | None = None,
) -> None:
    if _otel_logger is not None:
        try:
            _otel_logger.emit(
                severity_text="INFO",
                body=sanitize_value(body) if body is not None else event_name,
                attributes=_safe_attributes(attributes),
                context=context,
            )
        except Exception:
            # Ошибка экспорта телеметрии не должна прерывать HTTP-запрос приложения.
            return


def http_body_capture_enabled() -> bool:
    return get_settings().capture_http_bodies


class HttpBodyCaptureMiddleware:
    """Emit one bounded, redacted structured log record per incoming HTTP exchange."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        request_body = bytearray()
        request_overflow = False
        response_body = bytearray()
        response_overflow = False
        request_headers = scope.get("headers", [])
        response_headers: list[tuple[bytes, bytes]] = []
        status_code: int | None = None
        request_content_type = ""
        response_content_type = ""
        captured = http_body_capture_enabled()

        async def receive_capture() -> dict[str, Any]:
            nonlocal request_overflow
            message = cast(dict[str, Any], await receive())
            if message["type"] == "http.request" and captured:
                chunk = message.get("body", b"")
                if len(request_body) + len(chunk) > MAX_BODY_BYTES:
                    request_overflow = True
                elif not request_overflow:
                    request_body.extend(chunk)
            return message

        async def send_capture(message: dict[str, Any]) -> None:
            nonlocal request_content_type, response_content_type, response_overflow
            nonlocal response_headers, status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                response_headers = message.get("headers", [])
                headers = _safe_headers_map(response_headers)
                response_content_type = next(
                    (value for key, value in headers.items() if key.lower() == "content-type"),
                    "",
                )
                request_headers_map = _safe_headers_map(request_headers)
                request_content_type = next(
                    (
                        value
                        for key, value in request_headers_map.items()
                        if key.lower() == "content-type"
                    ),
                    "",
                )
                span = trace.get_current_span()
                if span.is_recording():
                    span.set_attribute("http.response.status_code", status_code or 0)
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if not captured:
                    pass
                elif len(response_body) + len(chunk) > MAX_BODY_BYTES:
                    response_overflow = True
                elif not response_overflow:
                    response_body.extend(chunk)
                if not message.get("more_body", False):
                    request_value, request_truncated = _structured_body_value(
                        request_content_type,
                        bytes(request_body) if captured else None,
                        overflow=request_overflow,
                    )
                    response_value, response_truncated = _structured_body_value(
                        response_content_type,
                        bytes(response_body) if captured else None,
                        overflow=response_overflow,
                    )
                    ids = _request_context_ids(request_value)
                    if not ids.get("conversation_id") and isinstance(response_value, dict):
                        events = response_value.get("events")
                        if isinstance(events, list):
                            for event in events:
                                data = event.get("data") if isinstance(event, dict) else None
                                if isinstance(data, dict) and isinstance(
                                    data.get("conversation_id"), str
                                ):
                                    ids["conversation_id"] = data["conversation_id"]
                                    break
                    emit_http_exchange(
                        direction="inbound",
                        method=scope.get("method", ""),
                        url=_http_url(scope),
                        request_headers=request_headers,
                        request_body=request_value,
                        request_body_truncated=request_truncated,
                        status_code=status_code,
                        response_headers=response_headers,
                        response_body=response_value,
                        response_body_truncated=response_truncated,
                        request_context=ids,
                    )
            await send(message)

        await self.app(scope, receive_capture, send_capture)


def _configure(app: FastAPI) -> None:
    global _provider, _logger_provider, _otel_logger
    settings = get_settings()
    if not settings.otel_enabled:
        return
    from opentelemetry._logs import get_logger, set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import SpanLimits, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

    endpoint = settings.otel_exporter_endpoint
    resource = Resource.create({"service.name": settings.otel_service_name})
    _provider = TracerProvider(
        resource=resource, span_limits=SpanLimits(max_attribute_length=MAX_BODY_BYTES)
    )

    class SanitizingExporter(SpanExporter):
        def __init__(self) -> None:
            self._delegate = OTLPSpanExporter(endpoint=endpoint, insecure=True)

        def export(self, spans: Any) -> Any:
            return self._delegate.export(_safe_spans(spans))

        def shutdown(self) -> None:
            self._delegate.shutdown()

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return bool(self._delegate.force_flush(timeout_millis))

    _provider.add_span_processor(BatchSpanProcessor(SanitizingExporter()))
    trace.set_tracer_provider(_provider)
    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(_logger_provider)
    _otel_logger = get_logger("copia.http")
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=_provider, http_capture_headers_server_request=[]
    )
    app.add_middleware(HttpBodyCaptureMiddleware)
    HTTPXClientInstrumentor().instrument(
        tracer_provider=_provider, request_hook=_httpx_request, response_hook=_httpx_response
    )


def _httpx_request(span: Any, request: Any) -> None:
    if span:
        request.extensions["copia.otel.span_context"] = trace.set_span_in_context(span)
    if span and span.is_recording():
        span.set_attribute("http.request.headers.safe", _safe_headers(request.headers))
        span.set_attribute("url.full", sanitize_url(str(request.url)))


def _httpx_response(span: Any, request: Any, response_info: Any) -> None:
    response_headers = response_info.headers or {}
    if span and span.is_recording():
        span.set_attribute("http.response.status_code", response_info.status_code)
        span.set_attribute("http.response.headers.safe", _safe_headers(response_headers))
        span.set_attribute("http.response.body_captured", False)


def instrument_app(app: FastAPI) -> None:
    _configure(app)


def shutdown() -> None:
    if _provider is not None:
        _provider.shutdown()
    if _logger_provider is not None:
        _logger_provider.shutdown()


def _safe_asgi_headers(headers: list[tuple[bytes, bytes]]) -> str:
    return _safe_headers({key.decode("latin-1"): value.decode("latin-1") for key, value in headers})
