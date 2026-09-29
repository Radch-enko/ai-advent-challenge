from __future__ import annotations

import inspect
import json
import re
import uuid
from threading import Lock

from fastapi.testclient import TestClient

from copia.providers.domain.models.llm_stream_event import LLMStreamEvent

_stream_patch_lock = Lock()
_patched_router = None
_active_patches = 0
_had_instance_stream = False
_original_instance_stream = None


class ConversationTestResponse:
    def __init__(self, response, payload, status_code: int) -> None:
        self._response = response
        self._payload = payload
        self.status_code = status_code
        self.text = response.text
        self.headers = response.headers

    def json(self):
        return self._payload


class ConversationTestClient(TestClient):
    def post(self, url, *args, **kwargs):
        command = _legacy_command(url, kwargs.get("json"))
        if command is None:
            return super().post(url, *args, **kwargs)

        from copia import service

        provider_router = service.router
        patch_stream = _begin_stream_patch(provider_router)
        try:
            response = super().post("/conversation", json=command)
        finally:
            if patch_stream:
                _end_stream_patch(provider_router)
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            return response

        events = []
        current = {"event": "message", "data": ""}
        for line in response.text.splitlines():
            if line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] += line[6:]
            elif not line and current["data"]:
                events.append({"event": current["event"], "data": json.loads(current["data"])})
                current = {"event": "message", "data": ""}
        terminal = next(
            (
                event
                for event in reversed(events)
                if event["event"] in {"conversation.completed", "conversation.failed"}
            ),
            None,
        )
        if terminal is None:
            return ConversationTestResponse(response, {}, response.status_code)
        data = terminal["data"]
        if terminal["event"] == "conversation.completed":
            return ConversationTestResponse(response, data.get("result"), 200)
        code = data.get("code", "conversation_failed")
        status_code = int(data.get("http_status") or (409 if code == "task_active" else 502))
        return ConversationTestResponse(
            response,
            {
                "detail": {
                    "code": code,
                    "message": data.get("message", "Conversation failed"),
                    **({"status_code": data["http_status"]} if data.get("http_status") else {}),
                }
            },
            status_code,
        )


def _legacy_command(url: str, body):
    payload = body if isinstance(body, dict) else {}
    match = re.fullmatch(r"/sessions/([^/]+)/messages", url)
    if match:
        return {
            "command": "message",
            "request_id": str(uuid.uuid4()),
            "target": {"kind": "session", "id": match.group(1)},
            "content": payload.get("content", ""),
            "config": payload.get("config"),
        }
    match = re.fullmatch(r"/agents/([^/]+)/messages", url)
    if match:
        return {
            "command": "message",
            "request_id": str(uuid.uuid4()),
            "target": {"kind": "agent", "id": match.group(1)},
            "content": payload.get("content", ""),
        }
    match = re.fullmatch(r"/sessions/([^/]+)/summarization/retry", url)
    if match:
        return {
            "command": "retry_summarization",
            "request_id": str(uuid.uuid4()),
            "session_id": match.group(1),
        }
    if url == "/completions":
        return {"command": "completion", "request_id": str(uuid.uuid4()), **payload}
    return None


def _begin_stream_patch(provider_router) -> bool:
    global _active_patches, _had_instance_stream, _original_instance_stream, _patched_router
    with _stream_patch_lock:
        if _active_patches and _patched_router is provider_router:
            _active_patches += 1
            return True
        attributes = getattr(provider_router, "__dict__", {})
        had_instance_stream = "stream" in attributes
        original_instance_stream = attributes.get("stream")
        is_inherited_method = getattr(
            original_instance_stream, "__self__", None
        ) is provider_router and getattr(original_instance_stream, "__func__", None) is getattr(
            type(provider_router), "stream", None
        )
        if had_instance_stream and not is_inherited_method:
            return False
        if _active_patches == 0:
            _patched_router = provider_router
            _had_instance_stream = had_instance_stream
            _original_instance_stream = original_instance_stream

            def fallback_stream(messages, config, tools=None):
                complete = provider_router.complete
                parameters = inspect.signature(complete).parameters
                response = (
                    complete(messages, config, tools)
                    if tools is not None and len(parameters) >= 3
                    else complete(messages, config)
                )
                if response.content:
                    yield LLMStreamEvent(kind="text_delta", text=response.content)
                yield LLMStreamEvent(kind="completed", response=response)

            provider_router.stream = fallback_stream
        elif _patched_router is not provider_router:
            return False
        _active_patches += 1
        return True


def _end_stream_patch(provider_router) -> None:
    global _active_patches, _patched_router
    with _stream_patch_lock:
        if _patched_router is not provider_router:
            return
        _active_patches -= 1
        if _active_patches == 0:
            if _had_instance_stream:
                provider_router.stream = _original_instance_stream
            else:
                delattr(provider_router, "stream")
            _patched_router = None
