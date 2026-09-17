import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.agent_log_store import AgentLogStore
from copia.data.providers.http_logging import _redact_url
from copia.data.providers.llm import GigaChatProvider, OpenAIProvider, ProviderError
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.agent_log import AgentLogExchange
from copia.domain.models.config import AgentConfig, ChatMessage, LLMResponse, ProviderName
from copia.domain.services.agent_log_context import agent_log_turn
from copia.domain.services.router import LLMRouter


def _exchange(
    turn_id: str,
    session_id: str,
    *,
    created_at: datetime,
    request_body: bytes = b"request",
    response_body: bytes = b"response",
) -> AgentLogExchange:
    return AgentLogExchange(
        id=f"exchange-{created_at.timestamp()}",
        agent_turn_id=turn_id,
        session_id=session_id,
        operation="primary",
        provider="openai",
        model="model",
        method="POST",
        url="https://provider.test/chat",
        request_headers={},
        request_body=request_body,
        response_headers={},
        response_body=response_body,
        duration_seconds=0.01,
        created_at=created_at,
    )


def test_openai_logs_real_exchange_and_preserves_existing_hooks() -> None:
    seen_by_existing_hook: list[str] = []

    def existing_hook(request: httpx.Request) -> None:
        seen_by_existing_hook.append(request.method)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "model",
                "choices": [{"message": {"content": "reply"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [existing_hook]},
    )
    store = AgentLogStore()
    provider = OpenAIProvider(api_key="top-secret", client=client, log_store=store)
    turn_id = store.start_turn("session", "turn")

    with agent_log_turn("session", turn_id, provider="openai", model="model"):
        provider.complete(
            [ChatMessage(role="user", content="Hello")],
            AgentConfig(name="test", provider="openai", model="model"),
        )
    store.finish_turn(turn_id, provider="openai", model="model")

    turn = store.get_turn("session", turn_id)
    assert turn is not None
    assert seen_by_existing_hook == ["POST"]
    assert len(turn.exchanges) == 1
    exchange = turn.exchanges[0]
    assert exchange.method == "POST"
    assert exchange.status_code == 200
    assert exchange.request_headers["authorization"] == "[REDACTED]"
    assert json.loads(exchange.request_body or b"{}")["messages"] == [
        {"role": "user", "content": "Hello"}
    ]
    assert (
        json.loads(exchange.response_body or b"{}")["choices"][0]["message"]["content"] == "reply"
    )
    assert exchange.duration_seconds >= 0


def test_provider_error_and_transport_error_are_logged_without_duplicates() -> None:
    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, json={"error": {"secret": "value"}})

    store = AgentLogStore()
    provider = OpenAIProvider(
        api_key="key",
        client=httpx.Client(transport=httpx.MockTransport(error_handler)),
        log_store=store,
    )
    turn_id = store.start_turn("session", "http-error")
    with agent_log_turn("session", turn_id, provider="openai", model="model"):
        with pytest.raises(ProviderError):
            provider.complete(
                [ChatMessage(role="user", content="Hello")],
                AgentConfig(name="test", provider="openai", model="model"),
            )
    store.finish_turn(turn_id, status="failed", error="provider failed")
    turn = store.get_turn("session", turn_id)
    assert turn is not None
    assert len(turn.exchanges) == 1
    assert turn.exchanges[0].status_code == 429
    assert b"value" not in (turn.exchanges[0].response_body or b"")
    assert b"[REDACTED]" in (turn.exchanges[0].response_body or b"")

    def transport_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Bearer leaked-secret", request=request)

    transport_store = AgentLogStore()
    transport_provider = OpenAIProvider(
        api_key="key",
        client=httpx.Client(transport=httpx.MockTransport(transport_error)),
        log_store=transport_store,
    )
    transport_turn_id = transport_store.start_turn("session", "transport-error")
    with agent_log_turn("session", transport_turn_id, provider="openai", model="model"):
        with pytest.raises(ProviderError):
            transport_provider.complete(
                [ChatMessage(role="user", content="Hello")],
                AgentConfig(name="test", provider="openai", model="model"),
            )
    transport_turn = transport_store.get_turn("session", transport_turn_id)
    assert transport_turn is not None
    assert len(transport_turn.exchanges) == 1
    assert transport_turn.exchanges[0].status_code is None
    assert "leaked-secret" not in (transport_turn.exchanges[0].error or "")


def test_gigachat_auth_exchange_is_excluded_and_user_body_is_visible() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "oauth" in str(request.url):
            return httpx.Response(200, request=request, json={"access_token": "token"})
        return httpx.Response(
            200,
            request=request,
            json={"model": "GigaChat", "choices": [{"message": {"content": "reply"}}]},
        )

    store = AgentLogStore()
    provider = GigaChatProvider(
        auth_key="basic-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        log_store=store,
    )
    turn_id = store.start_turn("session", "gigachat-turn")
    with agent_log_turn("session", turn_id, provider="gigachat", model="GigaChat"):
        provider.complete(
            [ChatMessage(role="user", content="contains memory")],
            AgentConfig(name="test", provider="gigachat", model="GigaChat"),
        )

    turn = store.get_turn("session", turn_id)
    assert turn is not None
    assert len(calls) == 2
    assert all("oauth" not in url for url in [exchange.url for exchange in turn.exchanges])
    assert len(turn.exchanges) == 1
    assert b"contains memory" in (turn.exchanges[0].request_body or b"")
    assert b'"content":"reply"' in (turn.exchanges[0].response_body or b"")


def test_agent_log_store_is_bounded_session_scoped_and_blocks_late_append() -> None:
    store = AgentLogStore(max_turns=2, max_exchanges_per_turn=1, max_body_bytes=4)
    now = datetime.now(UTC)
    store.start_turn("session-a", "turn-a")
    assert store.append(_exchange("turn-a", "session-a", created_at=now, request_body=b"123456"))
    store.finish_turn("turn-a")
    snapshot = store.get_turn("session-a", "turn-a")
    assert snapshot is not None
    assert snapshot.exchanges[0].request_body == b"1234"
    assert snapshot.exchanges[0].request_body_truncated is True
    snapshot.exchanges[0].request_headers["mutated"] = "snapshot-only"
    assert "mutated" not in store.get_turn("session-a", "turn-a").exchanges[0].request_headers  # type: ignore[union-attr]
    store.start_turn("session-b", "turn-b")
    store.start_turn("session-c", "turn-c")
    assert store.get_turn("session-a", "turn-a") is None
    assert store.get_turn("session-b", "turn-b") is not None

    store.delete_session("session-b")
    assert store.get_turn("session-b", "turn-b") is None
    assert not store.append(
        _exchange(
            "turn-b",
            "session-b",
            created_at=now + timedelta(seconds=1),
        )
    )
    assert store.get_turn("session-c", "turn-c") is not None
    assert _redact_url("https://provider.test/?api_key=secret&ok=yes") == (
        "https://provider.test/?api_key=[REDACTED]&ok=yes"
    )


def test_session_message_returns_log_id_and_detail_is_lazy_and_scoped(
    monkeypatch, tmp_path
) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    service.agent_log_store.clear()

    def complete(messages, config):
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(service.router, "complete", complete)
    client = TestClient(app)
    created = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    )
    session_id = created.json()["id"]
    response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})

    assert response.status_code == 200
    payload = response.json()
    log_id = payload["agent_log_id"]
    assert payload["response"]["trace"] is None
    assert "request_body" not in payload["response"]

    detail = client.get(f"/sessions/{session_id}/agent-logs/{log_id}")
    assert detail.status_code == 200
    assert detail.json()["agent_log_id"] == log_id
    assert detail.json()["status"] == "completed"
    other_session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]
    assert client.get(f"/sessions/{other_session_id}/agent-logs/{log_id}").status_code == 404

    assert client.delete(f"/sessions/{session_id}").status_code == 204
    assert client.get(f"/sessions/{session_id}/agent-logs/{log_id}").status_code == 404


def test_real_session_worker_groups_primary_classifier_and_title_calls(
    monkeypatch, tmp_path
) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    service.agent_log_store.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        schema = payload.get("response_format", {}).get("json_schema", {}).get("schema", {})
        if "candidates" in schema.get("properties", {}):
            content = '{"candidates": []}'
        elif "title" in schema.get("properties", {}):
            content = '{"title": "Test chat"}'
        else:
            content = "reply"
        return httpx.Response(
            200,
            request=request,
            json={"model": "model", "choices": [{"message": {"content": content}}]},
        )

    provider = OpenAIProvider(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        log_store=service.agent_log_store,
    )
    monkeypatch.setattr(
        service,
        "router",
        LLMRouter({ProviderName.OPENAI: provider}, agent_log_store=service.agent_log_store),
    )
    client = TestClient(app)
    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})

    assert response.status_code == 200
    log_id = response.json()["agent_log_id"]
    detail = service.agent_log_store.get_turn(session_id, log_id)
    assert detail is not None
    assert {exchange.operation for exchange in detail.exchanges} == {
        "memory_classification",
        "primary",
        "title",
    }
    assert {exchange.agent_turn_id for exchange in detail.exchanges} == {log_id}
    serialized = client.get(f"/sessions/{session_id}/agent-logs/{log_id}").json()
    assert all("test-key" not in json.dumps(exchange) for exchange in serialized["exchanges"])
    assert serialized["exchanges"][0]["request_body"]["encoding"] == "utf-8"


def test_session_provider_failure_returns_only_safe_trace_and_log_id(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    service.agent_log_store.clear()

    def fail(messages, config):
        raise ProviderError(
            "provider leaked-secret",
            status_code=503,
            request_body={"api_key": "leaked-secret"},
            response_body={"secret": "leaked-secret"},
        )

    monkeypatch.setattr(service.router, "complete", fail)
    client = TestClient(app)
    session_id = client.post(
        "/sessions", json={"config": {"name": "Copia", "provider": "openai", "model": "model"}}
    ).json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})

    assert response.status_code == 502
    payload = response.json()
    assert payload["detail"]["agent_log_id"]
    assert "leaked-secret" not in json.dumps(payload)
    detail = client.get(f"/sessions/{session_id}/agent-logs/{payload['detail']['agent_log_id']}")
    assert detail.json()["status"] == "failed"
