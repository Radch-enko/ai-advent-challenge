from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest

from copia.common.observability import (
    MAX_BODY_BYTES,
    HttpBodyCaptureMiddleware,
    _body_value,
    _httpx_response,
    _safe_attributes,
    _safe_spans,
)
from copia.providers.data.http_logging import record_response


def test_json_body_redacts_nested_secrets_before_capture() -> None:
    body, truncated = _body_value(
        "application/json",
        b'{"message":"hello","nested":{"api_key":"hidden","value":"safe"}}',
    )

    assert body is not None
    assert "hidden" not in body
    assert "[REDACTED]" in body
    assert "safe" in body
    assert truncated is False


def test_oversized_body_is_skipped_without_exporting_a_partial_secret() -> None:
    body, truncated = _body_value(
        "text/plain",
        ("Authorization: Bearer abcdefghijklmnop " + "x" * MAX_BODY_BYTES).encode(),
    )

    assert body is None
    assert truncated is True


def test_binary_and_invalid_json_bodies_are_skipped() -> None:
    assert _body_value("application/octet-stream", b"bytes") == (None, False)
    assert _body_value("application/json", b"not-json") == (None, False)


def test_log_attributes_redact_sensitive_keys_and_url_query_values() -> None:
    safe = _safe_attributes(
        {
            "authorization": "Bearer secret-value",
            "url.full": "https://example.test/path?api_key=secret-value",
            "detail": "api_key=secret-value",
        }
    )

    assert "secret-value" not in str(safe)
    assert safe["authorization"] == "[REDACTED]"


def test_httpx_response_hook_accepts_response_info_without_reading_stream() -> None:
    class RecordingSpan:
        attributes: dict[str, object]

        def __init__(self) -> None:
            self.attributes = {}

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attributes[key] = value

    span = RecordingSpan()
    request = httpx.Request("GET", "https://provider.test/models")
    response_info = SimpleNamespace(
        status_code=200,
        headers=httpx.Headers({"content-type": "application/json", "x-api-key": "hidden"}),
        stream=object(),
        extensions={},
    )

    _httpx_response(span, request, response_info)

    assert span.attributes["http.response.status_code"] == 200
    assert "hidden" not in str(span.attributes["http.response.headers.safe"])
    assert span.attributes["http.response.body_captured"] is False


def test_span_sanitizer_supports_non_dataclass_readable_spans() -> None:
    @dataclass
    class Event:
        name: str
        attributes: dict[str, str]

    @dataclass
    class Status:
        description: str

    span = SimpleNamespace(
        attributes={"api_key": "hidden", "url.full": "https://example.test/?token=hidden"},
        events=(Event("request", {"authorization": "Bearer hidden"}),),
        status=Status("api_key=hidden"),
        name="client request",
    )

    (safe_span,) = _safe_spans([span])

    assert safe_span.name == "client request"
    assert safe_span.attributes["api_key"] == "[REDACTED]"
    assert "hidden" not in str(safe_span.attributes)
    assert "hidden" not in str(safe_span.events)
    assert "hidden" not in safe_span.status.description


def test_provider_completed_response_log_includes_headers_body_and_masks_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import copia.common.observability as observability

    monkeypatch.setenv("COPIA_OTEL_CAPTURE_HTTP_BODIES", "true")

    class RecordingLogger:
        emitted: list[dict[str, object]]

        def __init__(self) -> None:
            self.emitted = []

        def emit(self, **record: object) -> None:
            self.emitted.append(record)

    logger = RecordingLogger()
    monkeypatch.setattr(observability, "_otel_logger", logger)
    request = httpx.Request(
        "POST",
        "https://provider.test/chat?api_key=secret",
        headers={"Authorization": "Bearer secret", "content-type": "application/json"},
        json={"messages": [{"role": "user", "content": "private text"}]},
    )
    response = httpx.Response(
        200,
        headers={"content-type": "application/json", "set-cookie": "secret-cookie"},
        json={"choices": [{"message": {"content": "reply"}}], "api_key": "secret"},
        request=request,
    )
    response.read()

    record_response(response)

    record = logger.emitted[0]
    body = record["body"]
    assert isinstance(body, dict)
    assert body["event"] == "http.exchange"
    assert body["direction"] == "outbound"
    assert body["request"]["body"]["messages"][0]["content"] == "private text"
    assert body["response"]["body"]["choices"][0]["message"]["content"] == "reply"
    assert body["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert body["response"]["headers"]["set-cookie"] == "[REDACTED]"
    attributes = record["attributes"]
    assert isinstance(attributes, dict)
    assert attributes["event.name"] == "http.exchange"
    assert "private text" not in str(attributes)
    assert "secret" not in str(attributes)


def test_inbound_middleware_logs_request_and_streamed_response_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import copia.common.observability as observability

    class RecordingLogger:
        emitted: list[dict[str, object]]

        def __init__(self) -> None:
            self.emitted = []

        def emit(self, **record: object) -> None:
            self.emitted.append(record)

    logger = RecordingLogger()
    monkeypatch.setattr(observability, "_otel_logger", logger)
    monkeypatch.setenv("COPIA_OTEL_CAPTURE_HTTP_BODIES", "true")
    incoming = [{"type": "http.request", "body": b'{"message":"private text"}', "more_body": False}]
    outgoing: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return incoming.pop(0)

    async def send(message: dict[str, object]) -> None:
        outgoing.append(message)

    async def app(scope: dict[str, object], receive_fn: object, send_fn: object) -> None:
        await receive_fn()
        await send_fn(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        await send_fn(
            {
                "type": "http.response.body",
                "body": b'data: {"reply":"visible"}\n\n',
                "more_body": True,
            }
        )
        await send_fn(
            {"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False}
        )

    scope: dict[str, object] = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    asyncio.run(HttpBodyCaptureMiddleware(app)(scope, receive, send))

    assert len(logger.emitted) == 1
    record = logger.emitted[0]
    body = record["body"]
    assert isinstance(body, dict)
    assert body["event"] == "http.exchange"
    assert body["request"]["body"]["message"] == "private text"
    assert body["response"]["body"]["events"] == [
        {"data": {"reply": "visible"}},
        {"data": "[DONE]"},
    ]
    assert body["response"]["headers"]["content-type"] == "text/event-stream"
    assert len(outgoing) == 3


def test_mcp_stream_completion_logs_sse_body_and_redacts_secret_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import httpx2

    import copia.common.observability as observability
    from copia.mcp.data.mcp_transport import _LimitedResponseStream

    class RecordingLogger:
        emitted: list[dict[str, object]]

        def __init__(self) -> None:
            self.emitted = []

        def emit(self, **record: object) -> None:
            self.emitted.append(record)

    class Stream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"api_key":"private-secret","result":"visible"}\n\n'

        async def aclose(self) -> None:
            return None

    logger = RecordingLogger()
    monkeypatch.setattr(observability, "_otel_logger", logger)
    monkeypatch.setenv("COPIA_OTEL_CAPTURE_HTTP_BODIES", "true")
    request = httpx2.Request(
        "POST",
        "https://mcp.example/mcp",
        headers={"content-type": "application/json", "authorization": "Bearer private-secret"},
        json={"method": "tools/call", "params": {"arguments": {"query": "visible"}}},
    )
    response = httpx2.Response(
        200,
        headers={"content-type": "text/event-stream", "x-api-key": "private-secret"},
        stream=Stream(),
        request=request,
    )
    wrapped = _LimitedResponseStream(
        response.stream,
        request=request,
        response=response,
        span_context=None,
    )

    async def consume() -> list[bytes]:
        return [chunk async for chunk in wrapped]

    chunks = asyncio.run(consume())

    assert len(chunks) == 1
    assert len(logger.emitted) == 1
    record = logger.emitted[0]
    body = record["body"]
    assert isinstance(body, dict)
    assert body["event"] == "http.exchange"
    assert body["direction"] == "outbound"
    assert body["request"]["body"]["params"]["arguments"]["query"] == "visible"
    assert body["response"]["body"]["events"] == [
        {"data": {"api_key": "[REDACTED]", "result": "visible"}}
    ]
    assert body["request"]["headers"]["authorization"] == "[REDACTED]"
    assert body["response"]["headers"]["x-api-key"] == "[REDACTED]"
    attributes = record["attributes"]
    assert isinstance(attributes, dict)
    assert "private-secret" not in str(attributes)
