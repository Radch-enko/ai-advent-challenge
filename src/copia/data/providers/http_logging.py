from __future__ import annotations

import time
from datetime import UTC, datetime
from functools import partial

import httpx

from ...domain.contracts import AgentLogSink
from ...domain.models.agent_log import AgentLogContext, AgentLogExchange
from ...domain.services.agent_log_context import current_agent_log_context
from ...domain.services.credential_sanitizer import (
    is_sensitive_key,
    sanitize_error,
    sanitize_text,
    sanitize_url,
)

_STARTED_AT = "copia.agent_log.started_at"
_CONTEXT = "copia.agent_log.context"
_REQUEST_BODY = "copia.agent_log.request_body"
_SKIP = "copia.agent_log.skip"
_RESPONSE_RECORDED = "copia.agent_log.response_recorded"
_SENSITIVE_HEADER_PARTS = (
    "authorization",
    "api-key",
    "apikey",
    "auth-key",
    "authkey",
    "cookie",
    "client-secret",
    "clientsecret",
    "id-token",
    "idtoken",
    "set-cookie",
    "access-token",
    "refresh-token",
    "token",
    "password",
    "secret",
    "www-authenticate",
    "proxy-authenticate",
)


def install_http_logging(client: httpx.Client, store: AgentLogSink) -> None:
    """Append transport hooks without replacing hooks supplied by callers."""
    marker = "_copia_agent_log_store"
    if getattr(client, marker, None) is store:
        return
    setattr(client, marker, store)
    client.event_hooks.setdefault("request", []).append(partial(_request_hook, store))
    client.event_hooks.setdefault("response", []).append(partial(_response_hook, store))


def record_transport_error(
    store: AgentLogSink, request: httpx.Request, error: BaseException
) -> None:
    try:
        context = _context_for_request(request)
        if context is None or request.extensions.get(_SKIP) or _is_auth_endpoint(request.url):
            return
        body = request.extensions.get(_REQUEST_BODY)
        request_truncated = bool(request.extensions.get("copia.agent_log.request_body_truncated"))
        if not isinstance(body, bytes):
            body, request_truncated = _capture_body(store, _request_content(request))
        _append_exchange(
            store,
            context=context,
            request=request,
            request_body=body,
            request_body_truncated=request_truncated,
            response=None,
            duration_seconds=_duration_for(request),
            error=_safe_error(str(error)),
        )
    except Exception:
        return


def _request_hook(store: AgentLogSink, request: httpx.Request) -> None:
    try:
        context = current_agent_log_context()
        if context is None:
            return
        request.extensions[_STARTED_AT] = time.perf_counter()
        request.extensions[_CONTEXT] = context
        request.extensions["copia.agent_log.store"] = store
        if _is_auth_endpoint(request.url):
            request.extensions[_SKIP] = True
            return
        body, truncated = _capture_body(store, _request_content(request))
        request.extensions[_REQUEST_BODY] = body
        request.extensions["copia.agent_log.request_body_truncated"] = truncated
    except Exception:
        return


def _response_hook(store: AgentLogSink, response: httpx.Response) -> None:
    try:
        request = response.request
        context = _context_for_request(request)
        if (
            context is None
            or request.extensions.get(_SKIP)
            or _is_auth_endpoint(request.url)
            or request.extensions.get(_RESPONSE_RECORDED)
        ):
            return
        # Sync httpx response hooks can run before Client.send() loads the body.
        # Never force a read here: providers parse their own response after send.
        if not response.is_stream_consumed:
            return
        request_body = request.extensions.get(_REQUEST_BODY)
        request_truncated = bool(request.extensions.get("copia.agent_log.request_body_truncated"))
        if not isinstance(request_body, bytes):
            request_body, request_truncated = _capture_body(store, _request_content(request))
        response_body, response_truncated = _capture_body(store, response.content)
        _append_exchange(
            store,
            context=context,
            request=request,
            request_body=request_body,
            request_body_truncated=request_truncated,
            response=response,
            response_body=response_body,
            response_body_truncated=response_truncated,
            duration_seconds=_duration_for(request),
            error=None,
        )
        request.extensions[_RESPONSE_RECORDED] = True
    except Exception:
        return


def record_response(store: AgentLogSink, response: httpx.Response) -> None:
    """Capture a provider response after the synchronous client has loaded it."""
    try:
        request = response.request
        context = _context_for_request(request)
        if (
            context is None
            or request.extensions.get(_SKIP)
            or request.extensions.get(_RESPONSE_RECORDED)
            or _is_auth_endpoint(request.url)
        ):
            return
        request_body = request.extensions.get(_REQUEST_BODY)
        request_truncated = bool(request.extensions.get("copia.agent_log.request_body_truncated"))
        if not isinstance(request_body, bytes):
            request_body, request_truncated = _capture_body(store, _request_content(request))
        if not response.is_stream_consumed:
            return
        response_body, response_truncated = _capture_body(store, response.content)
        _append_exchange(
            store,
            context=context,
            request=request,
            request_body=request_body,
            request_body_truncated=request_truncated,
            response=response,
            response_body=response_body,
            response_body_truncated=response_truncated,
            duration_seconds=_duration_for(request),
            error=None,
        )
        request.extensions[_RESPONSE_RECORDED] = True
    except Exception:
        return


def _append_exchange(
    store: AgentLogSink,
    *,
    context: AgentLogContext,
    request: httpx.Request,
    request_body: bytes | None,
    request_body_truncated: bool,
    response: httpx.Response | None,
    response_body: bytes | None = None,
    response_body_truncated: bool = False,
    duration_seconds: float,
    error: str | None,
) -> None:
    _ensure_store(store)
    store.append(
        AgentLogExchange(
            id=_new_id(),
            agent_turn_id=context.agent_turn_id,
            session_id=context.session_id,
            operation=context.operation,
            provider=context.provider,
            model=context.model,
            method=request.method,
            url=_redact_url(str(request.url)),
            request_headers=_redact_headers(request.headers),
            request_body=request_body,
            request_body_truncated=request_body_truncated,
            status_code=response.status_code if response is not None else None,
            response_headers=(_redact_headers(response.headers) if response is not None else {}),
            response_body=response_body,
            response_body_truncated=response_body_truncated,
            duration_seconds=max(0, duration_seconds),
            error=_safe_error(error) if error else None,
            created_at=datetime.now(UTC),
        )
    )


def _context_for_request(request: httpx.Request) -> AgentLogContext | None:
    context = request.extensions.get(_CONTEXT)
    if isinstance(context, AgentLogContext):
        return context
    return current_agent_log_context()


def _ensure_store(store: AgentLogSink) -> None:
    # Kept as a small seam for tests and to make the append boundary explicit.
    if not isinstance(store, AgentLogSink):
        raise TypeError("Agent log store is invalid")


def _request_content(request: httpx.Request) -> bytes | None:
    try:
        return request.content
    except httpx.RequestNotRead:
        return None


def _capture_body(store: AgentLogSink, body: bytes | None) -> tuple[bytes | None, bool]:
    if body is None:
        return None, False
    # Redact the complete payload first. Truncating before this step could leave
    # a profile value in the retained prefix when the closing delimiter is past
    # the body limit.
    redacted = _redacted_body(body)
    if redacted is None:
        return None, len(body) > store.max_body_bytes
    truncated = len(redacted) > store.max_body_bytes
    return redacted[: store.max_body_bytes], truncated


def _redacted_body(body: bytes | None) -> bytes | None:
    if body is None:
        return None
    try:
        text = body.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        # Preserve binary payloads for educational inspection while still
        # allowing the credential patterns below to be removed.
        text = body.decode("latin-1")
        encoding = "latin-1"

    text = sanitize_text(text)
    return text.encode(encoding)


def _redact_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        name: "[REDACTED]" if _is_sensitive_header(name) else value
        for name, value in headers.items()
    }


def _is_sensitive_header(name: str) -> bool:
    normalized = name.lower()
    return is_sensitive_key(name) or any(part in normalized for part in _SENSITIVE_HEADER_PARTS)


def redact_url(url: str) -> str:
    return sanitize_url(url)


def redact_url_text(value: str) -> str:
    """Apply URL redaction to embedded URLs without changing ordinary text."""
    return sanitize_text(value)


def _redact_url(url: str) -> str:
    """Backward-compatible private alias for existing callers and tests."""
    return redact_url(url)


def _is_auth_endpoint(url: httpx.URL) -> bool:
    path = url.path.lower().rstrip("/")
    return "/oauth" in path or path.endswith("/token")


def _duration_for(request: httpx.Request) -> float:
    started_at = request.extensions.get(_STARTED_AT)
    return time.perf_counter() - started_at if isinstance(started_at, float) else 0


def _safe_error(value: str) -> str:
    return sanitize_error(value)


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
