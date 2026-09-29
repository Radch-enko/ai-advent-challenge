from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from copia import service
from copia.conversations.application.conversation_run import ConversationEventLimitExceeded
from copia.conversations.application.conversation_store import ConversationStore
from copia.conversations.data.conversation_repository import ConversationRepository
from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.llm_stream_event import LLMStreamEvent
from copia.providers.domain.models.provider_name import ProviderName
from copia.sessions.api.models.session_llm_response import SessionLLMResponse
from copia.sessions.api.models.session_message_response import SessionMessageResponse
from copia.sessions.domain.models.chat_session import ChatSession


def test_completion_streams_typed_events_and_deduplicates_request(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(service, "conversation_store", store)
    calls = 0

    def stream(_messages, config, _tools=None):
        nonlocal calls
        calls += 1
        yield LLMStreamEvent(kind="text_delta", text="Hello")
        yield LLMStreamEvent(
            kind="completed",
            response=LLMResponse(content="Hello", provider=ProviderName.OPENAI, model=config.model),
        )

    monkeypatch.setattr(service.router, "stream", stream)
    client = TestClient(service.app)
    payload = {
        "command": "completion",
        "request_id": "request-1",
        "config": {"provider": "openai", "model": "test-model"},
        "messages": [{"role": "user", "content": "Hi"}],
    }

    first = client.post("/conversation", json=payload)
    second = client.post("/conversation", json=payload)

    assert first.status_code == second.status_code == 200
    assert "event: message.delta" in first.text
    assert 'data: {"text":"Hello"}' in first.text
    assert "event: conversation.completed" in first.text
    assert calls == 1


def test_session_message_command_emits_incremental_text(monkeypatch) -> None:
    session = ChatSession(
        id="session-stream",
        config={"name": "Copia", "provider": "openai", "model": "test-model"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def get_session(_session_id):
        return session

    async def validate(_session_id):
        return None

    async def send(_session_id, _request, emit):
        emit("message.delta", {"text": "Hi "})
        emit("message.delta", {"text": "there"})
        return SessionMessageResponse(
            response=SessionLLMResponse(
                content="Hi there", provider=ProviderName.OPENAI, model="test-model"
            ),
            duration_seconds=0.1,
        )

    monkeypatch.setattr(service, "_get_session", get_session)
    monkeypatch.setattr(service.session_message_routes, "validate_streaming_message", validate)
    monkeypatch.setattr(service.session_message_routes, "execute_streaming_message", send)

    response = TestClient(service.app).post(
        "/conversation",
        json={
            "command": "message",
            "request_id": "session-message-1",
            "target": {"kind": "session", "id": session.id},
            "content": "Hi",
        },
    )

    assert response.status_code == 200
    assert response.text.count("event: message.delta") == 2
    assert 'data: {"text":"Hi "}' in response.text
    assert 'data: {"text":"there"}' in response.text
    assert "event: conversation.completed" in response.text


def test_approval_decision_is_a_deduplicated_conversation_command(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(service, "conversation_store", store)
    session = ChatSession(
        id="approval-session",
        config={"name": "Copia", "provider": "openai", "model": "test-model"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def get_session(_session_id):
        return session

    monkeypatch.setattr(service, "_get_session", get_session)
    turn, _ = store.create("mcp-request", {"command": "message"})
    turn.session_id = session.id
    turn.prepare_approval(
        McpApproval(
            id="approval-id",
            connection_id="connection",
            connection_name="MCP",
            tool_name="search",
            arguments={"query": "safe"},
        )
    )
    payload = {
        "command": "approval_decision",
        "request_id": "approval-request-1",
        "session_id": session.id,
        "approval_id": "approval-id",
        "decision": "approve",
    }
    client = TestClient(service.app)
    first = client.post("/conversation", json=payload)
    second = client.post("/conversation", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.text.count("event: approval.accepted") == 1
    assert second.text.count("event: approval.accepted") == 1
    assert turn.decision is True


def test_conversation_replay_and_old_routes_are_removed(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(service, "conversation_store", store)
    run, _ = store.create("replay-request", {"command": "completion"})
    run.emit("message.delta", {"text": "first"})
    run.emit("message.delta", {"text": "second"})
    run.emit("conversation.completed", {"conversation_id": run.id, "result": {}})

    response = TestClient(service.app).post(
        "/conversation",
        json={
            "command": "resume",
            "request_id": "resume-request",
            "conversation_id": run.id,
            "after_event_id": f"{run.id}:3",
        },
    )

    assert response.status_code == 200
    assert "event: conversation.completed" in response.text
    assert "first" not in response.text
    assert "second" not in response.text
    by_request = TestClient(service.app).post(
        "/conversation",
        json={"command": "resume", "request_id": "replay-request"},
    )
    assert by_request.status_code == 200
    assert "first" in by_request.text and "second" in by_request.text
    client = TestClient(service.app)
    for path, method in (
        ("/sessions/s/messages", "post"),
        ("/sessions/s/turns", "post"),
        ("/sessions/s/mcp-approvals/a", "post"),
        ("/completions", "post"),
        ("/sessions/s/summarization/retry", "post"),
        ("/agents/a/messages", "post"),
    ):
        assert getattr(client, method)(path, json={}).status_code == 404


def test_store_reloads_events_and_request_deduplication_after_restart(tmp_path) -> None:
    path = tmp_path / "conversations.sqlite3"
    first_store = ConversationStore(path)
    run, created = first_store.create("persistent-request", {"command": "completion"})
    run.emit("message.delta", {"text": "persisted"})
    run.emit("conversation.completed", {"conversation_id": run.id, "result": {}})

    restarted_store = ConversationStore(path)
    existing, created_after_restart = restarted_store.create(
        "persistent-request", {"command": "completion"}
    )

    assert created
    assert not created_after_restart
    assert existing.id == run.id
    assert [event["event"] for event in existing.events][-2:] == [
        "message.delta",
        "conversation.completed",
    ]


def test_expired_and_evicted_conversations_are_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ConversationRepository, "TTL_SECONDS", 24 * 60 * 60)
    monkeypatch.setattr(ConversationRepository, "MAX_CONVERSATIONS", 2)
    store = ConversationStore(tmp_path / "bounded.sqlite3")
    first, _ = store.create("bounded-1", {})
    first.emit("conversation.completed", {})
    second, _ = store.create("bounded-2", {})
    second.emit("conversation.completed", {})
    third, _ = store.create("bounded-3", {})

    assert store.get(first.id) is None
    assert store.get(second.id) is not None
    assert store.get(third.id) is not None

    monkeypatch.setattr(ConversationRepository, "TTL_SECONDS", 0)
    assert store.get(third.id) is None


def test_event_limit_ends_run_with_terminal_storage_error(monkeypatch) -> None:
    monkeypatch.setattr(ConversationRepository, "MAX_CONVERSATION_BYTES", 512)
    store = ConversationStore()
    run, _ = store.create("bounded-event", {})
    with pytest.raises(ConversationEventLimitExceeded):
        run.emit("message.delta", {"text": "x" * 1024})

    assert run.status == "failed"
    assert run.events[-1]["event"] == "conversation.failed"
    assert run.events[-1]["data"]["code"] == "conversation_storage_limit"


def test_errors_are_http_before_stream_and_sanitized_after_start(monkeypatch) -> None:
    client = TestClient(service.app)
    missing = client.post(
        "/conversation",
        json={
            "command": "message",
            "request_id": "missing-session",
            "target": {"kind": "session", "id": "missing"},
            "content": "Hi",
        },
    )
    assert missing.status_code == 404

    monkeypatch.setattr(
        service.router,
        "stream",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProviderError(
                "provider failed",
                request_body={"api_key": "request-secret"},
                response_body={"token": "response-secret"},
            )
        ),
    )
    failed = client.post(
        "/conversation",
        json={
            "command": "completion",
            "request_id": "failed-provider",
            "config": {"provider": "openai", "model": "test-model"},
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert failed.status_code == 200
    assert "event: conversation.failed" in failed.text
    assert "request-secret" not in failed.text
    assert "response-secret" not in failed.text
