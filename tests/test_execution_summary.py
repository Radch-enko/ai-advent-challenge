from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Event, Thread

from fastapi.testclient import TestClient

from copia import service
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession


def test_session_response_and_persisted_message_include_execution_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    monkeypatch.setattr(
        service.router,
        "complete",
        lambda _messages, config: LLMResponse(
            content="reply",
            provider=config.provider,
            model=config.model,
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        ),
    )
    client = TestClient(app)
    session_id = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "test-model"}},
    ).json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})

    assert response.status_code == 200
    assert response.json()["duration_seconds"] >= 0
    stored = client.get(f"/sessions/{session_id}").json()["messages"][-1]
    assert stored["provider"] == "openai"
    assert stored["model"] == "test-model"
    assert stored["execution_status"] == "completed"
    assert stored["usage"]["total_tokens"] == 7
    assert "agent_log_id" not in stored


def test_log_routes_are_removed_and_provider_error_payload_is_not_returned(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "sessions", SessionsRepository(tmp_path / "sessions"))
    client = TestClient(app)
    session_id = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "model"}},
    ).json()["id"]
    monkeypatch.setattr(
        service.router,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProviderError(
                "Provider request failed",
                status_code=502,
                request_body={"prompt": "private prompt", "api_key": "request-secret"},
                response_body={"response": "private response", "api_key": "response-secret"},
            )
        ),
    )

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "hello"})
    detail = json.dumps(response.json())

    assert response.status_code == 502
    assert "Provider request failed" in detail
    assert "request_body" not in detail and "response_body" not in detail
    assert "request-secret" not in detail and "response-secret" not in detail
    assert client.get(f"/sessions/{session_id}/agent-logs/not-a-log").status_code == 404
    assert client.get("/scheduled-jobs/summary/runs/latest/log").status_code == 404


def test_session_lock_cleanup_waits_for_blocked_users(monkeypatch, tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", repository)
    now = datetime.now(UTC)
    session = ChatSession(
        id="lock-cleanup-session",
        config={"name": "test", "provider": "openai", "model": "model"},
        created_at=now,
        updated_at=now,
    )
    repository.save(session)
    state = service._session_message_lock(session.id)
    state.lock.acquire()
    waiter_started = Event()
    waiter_finished = Event()

    def waiter() -> None:
        waiter_state = service._session_message_lock(session.id)
        waiter_started.set()
        waiter_state.lock.acquire()
        waiter_state.lock.release()
        service._release_session_message_lock(waiter_state)
        waiter_finished.set()

    waiter_thread = Thread(target=waiter)
    waiter_thread.start()
    assert waiter_started.wait(timeout=1)
    delete_thread = Thread(target=lambda: service.delete_session(session.id))
    delete_thread.start()
    state.lock.release()
    service._release_session_message_lock(state)
    delete_thread.join(timeout=2)
    waiter_thread.join(timeout=2)

    assert waiter_finished.is_set()
    assert session.id not in service.session_message_locks
