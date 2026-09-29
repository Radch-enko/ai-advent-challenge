from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

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


def _safe_headers(headers: Any) -> str:
    return json.dumps(
        {key: "[REDACTED]" if is_sensitive_key(key) else value for key, value in headers.items()},
        ensure_ascii=True,
    )


def _body_value(content_type: str, body: bytes) -> tuple[str | None, bool]:
    if not body or not ("json" in content_type.lower() or "text/" in content_type.lower()):
        return None, False
    if len(body) > MAX_BODY_BYTES:
        return None, True
    try:
        text = body.decode("utf-8")
        if "json" in content_type.lower():
            value = json.loads(text)
            text = json.dumps(sanitize_value(value), ensure_ascii=True)
        else:
            text = sanitize_text(text)
        return text[:MAX_BODY_BYTES], False
    except (UnicodeDecodeError, ValueError, TypeError):
        return None, False


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
    event_name: str, attributes: dict[str, Any], *, context: Any | None = None
) -> None:
    if _otel_logger is not None:
        try:
            _otel_logger.emit(
                severity_text="INFO",
                body=event_name,
                attributes=_safe_attributes(attributes),
                context=context,
            )
        except Exception:
            # Ошибка экспорта телеметрии не должна прерывать HTTP-запрос приложения.
            return


def http_body_capture_enabled() -> bool:
    return get_settings().capture_http_bodies


class HttpBodyCaptureMiddleware:
    """Capture bounded, redacted JSON/text payloads on the active HTTP span."""

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
        response_content_type = ""
        request_logged = False

        async def receive_capture() -> dict[str, Any]:
            nonlocal request_overflow
            message = await receive()
            if message["type"] == "http.request" and http_body_capture_enabled():
                chunk = message.get("body", b"")
                if len(request_body) + len(chunk) > MAX_BODY_BYTES:
                    request_overflow = True
                elif not request_overflow:
                    request_body.extend(chunk)
            return message

        async def send_capture(message: dict[str, Any]) -> None:
            nonlocal response_content_type, response_overflow, request_logged
            if message["type"] == "http.response.start":
                scope["_copia_status"] = message.get("status", 0)
                headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }
                scope["_copia_response_headers"] = _safe_asgi_headers(message.get("headers", []))
                response_content_type = headers.get("content-type", "")
                span = trace.get_current_span()
                if span.is_recording():
                    self._record(
                        span,
                        "http.request.body",
                        scope,
                        request_body,
                        request_overflow,
                        request=True,
                    )
                self._record_http_log(
                    "http.request", scope, request_body, request_overflow, request=True
                )
                request_logged = True
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if not http_body_capture_enabled():
                    pass
                elif len(response_body) + len(chunk) > MAX_BODY_BYTES:
                    response_overflow = True
                elif not response_overflow:
                    response_body.extend(chunk)
                if not message.get("more_body", False):
                    span = trace.get_current_span()
                    if span.is_recording():
                        if not request_logged:
                            self._record(
                                span,
                                "http.request.body",
                                scope,
                                request_body,
                                request_overflow,
                                request=True,
                            )
                        self._record(
                            span,
                            "http.response.body",
                            scope,
                            response_body,
                            response_overflow,
                            content_type=response_content_type,
                        )
                    if not request_logged:
                        self._record_http_log(
                            "http.request", scope, request_body, request_overflow, request=True
                        )
                    self._record_http_log(
                        "http.response",
                        scope,
                        response_body,
                        response_overflow,
                        content_type=response_content_type,
                    )
            await send(message)

        await self.app(scope, receive_capture, send_capture)

    @staticmethod
    def _record_http_log(
        name: str,
        scope: dict[str, Any],
        body: bytearray,
        overflow: bool,
        *,
        request: bool = False,
        content_type: str | None = None,
    ) -> None:
        headers = dict(scope.get("headers", []))
        media_type = (
            headers.get(b"content-type", b"").decode("latin-1") if request else content_type or ""
        )
        value, truncated = (None, True) if overflow else _body_value(media_type, bytes(body))
        attributes: dict[str, Any] = {
            "http.request.method": scope.get("method", ""),
            "url.path": scope.get("path", ""),
            "http.response.status_code": scope.get("_copia_status", 0),
            "url.full": sanitize_url(
                "http://localhost"
                + scope.get("path", "")
                + (
                    "?" + scope["query_string"].decode("latin-1")
                    if scope.get("query_string")
                    else ""
                )
            ),
            "http.request.headers.safe": _safe_asgi_headers(scope.get("headers", []))
            if request
            else "",
            "http.body.truncated": truncated,
        }
        if not request:
            attributes["http.response.content_type"] = content_type or ""
            attributes["http.response.headers.safe"] = scope.get("_copia_response_headers", "")
        if value is not None:
            attributes["http.request.body" if request else "http.response.body"] = value
        emit_http_log(name, attributes)

    @staticmethod
    def _record(
        span: Any,
        name: str,
        scope: dict[str, Any],
        body: bytearray,
        overflow: bool,
        *,
        request: bool = False,
        content_type: str | None = None,
    ) -> None:
        headers = dict(scope.get("headers", []))
        media_type = (
            headers.get(b"content-type", b"").decode("latin-1") if request else content_type or ""
        )
        if overflow:
            span.add_event(name, {"http.body.truncated": True})
            return
        value, truncated = _body_value(media_type, bytes(body))
        if value is not None:
            field = "http.request.body" if request else "http.response.body"
            span.add_event(name, {field: value, "http.body.truncated": truncated})


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
            return self._delegate.force_flush(timeout_millis)

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
    attributes: dict[str, Any] = {
        "http.request.method": request.method,
        "url.full": sanitize_url(str(request.url)),
        "http.request.headers.safe": _safe_headers(request.headers),
    }
    try:
        if http_body_capture_enabled():
            value, truncated = _body_value(request.headers.get("content-type", ""), request.content)
            if value is not None:
                attributes["http.request.body"] = value
            attributes["http.body.truncated"] = truncated
    except (AttributeError, RuntimeError):
        pass
    emit_http_log("http.client.request", attributes)
    if span and span.is_recording():
        span.set_attribute("http.request.headers.safe", _safe_headers(request.headers))
        span.set_attribute("url.full", sanitize_url(str(request.url)))
        if http_body_capture_enabled():
            try:
                body = request.content
                value, truncated = _body_value(request.headers.get("content-type", ""), body)
                if value is not None:
                    span.add_event(
                        "http.request.body",
                        {"http.request.body": value, "http.body.truncated": truncated},
                    )
            except (AttributeError, RuntimeError):
                pass


def _httpx_response(span: Any, request: Any, response_info: Any) -> None:
    response_headers = response_info.headers or {}
    attributes: dict[str, Any] = {
        "http.request.method": request.method,
        "url.full": sanitize_url(str(request.url)),
        "http.response.status_code": response_info.status_code,
        "http.response.headers.safe": _safe_headers(response_headers),
        "http.response.body_captured": False,
    }
    emit_http_log("http.client.response", attributes)
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
