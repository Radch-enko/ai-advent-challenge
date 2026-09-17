from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.sessions_repository import SessionsRepository
from copia.domain.models.config import AgentConfig, LLMResponse, ProviderTrace
from copia.domain.models.session import ChatSession
from copia.domain.services.router import ProviderError


def _facts_session(session_id: str) -> ChatSession:
    now = datetime.now(UTC)
    return ChatSession(
        id=session_id,
        config=AgentConfig.model_validate(
            {
                "name": "facts",
                "provider": "openai",
                "model": "main-model",
                "context_management": {
                    "strategy": "sticky_facts",
                    "facts_updater": {"model": "facts-model"},
                },
            }
        ),
        created_at=now,
        updated_at=now,
    )


def test_facts_only_success_redacts_primary_and_facts_traces(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    session = _facts_session("facts-success")
    sessions.save(session)
    sessions.save_facts(session.id, {"secret": "provider payload"})

    class Router:
        def complete(self, messages, config):
            if config.structured_output is not None:
                return LLMResponse(
                    content='{"updates": [], "deletions": []}',
                    structured_data={"updates": [], "deletions": []},
                    provider="openai",
                    model=config.model,
                    trace=ProviderTrace(
                        status_code=200,
                        request_body={"secret": "provider payload"},
                        response_body={"secret": "provider payload"},
                    ),
                )
            return LLMResponse(
                content="reply",
                provider="openai",
                model=config.model,
                trace=ProviderTrace(
                    status_code=200,
                    request_body={"secret": "provider payload"},
                    response_body={"secret": "provider payload"},
                ),
            )

    monkeypatch.setattr(service, "router", Router())
    response = TestClient(app).post(f"/sessions/{session.id}/messages", json={"content": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["response"]["trace"] is None
    assert body["facts_events"][0]["trace"]["request_body"]["redacted"]


def test_facts_only_provider_failure_redacts_error_trace(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    session = _facts_session("facts-failure")
    sessions.save(session)
    sessions.save_facts(session.id, {"secret": "provider payload"})

    class Router:
        def complete(self, messages, config):
            if config.structured_output is not None:
                return LLMResponse(
                    content='{"updates": [], "deletions": []}',
                    structured_data={"updates": [], "deletions": []},
                    provider="openai",
                    model=config.model,
                )
            raise ProviderError(
                "provider failed",
                status_code=503,
                request_body={"secret": "provider payload"},
                response_body={"secret": "provider payload"},
            )

    monkeypatch.setattr(service, "router", Router())
    response = TestClient(app).post(f"/sessions/{session.id}/messages", json={"content": "hello"})

    assert response.status_code == 502
    trace = response.json()["detail"]["provider_trace"]
    assert trace["request_body"]["redacted"]
    assert trace["response_body"]["redacted"]


def test_context_management_update_waits_for_in_flight_send(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    session = _facts_session("context-race")
    sessions.save(session)
    provider_started = Event()
    release_provider = Event()

    class Router:
        def complete(self, messages, config):
            provider_started.set()
            assert release_provider.wait(timeout=5)
            if config.structured_output is not None:
                return LLMResponse(
                    content='{"updates": [], "deletions": []}',
                    structured_data={"updates": [], "deletions": []},
                    provider="openai",
                    model=config.model,
                )
            return LLMResponse(content="reply", provider="openai", model=config.model)

    monkeypatch.setattr(service, "router", Router())
    client = TestClient(app)
    with ThreadPoolExecutor(max_workers=2) as executor:
        send = executor.submit(
            client.post, f"/sessions/{session.id}/messages", json={"content": "hello"}
        )
        assert provider_started.wait(timeout=5)
        update = executor.submit(
            client.patch,
            f"/sessions/{session.id}/context-management",
            json={"recent_message_limit": 3},
        )
        assert not update.done()
        release_provider.set()
        assert send.result(timeout=5).status_code == 200
        assert update.result(timeout=5).status_code == 200

    restored = sessions.load(session.id)
    assert restored is not None
    assert restored.config.context_management.recent_message_limit == 3
