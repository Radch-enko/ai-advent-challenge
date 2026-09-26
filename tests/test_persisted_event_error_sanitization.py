from fastapi.testclient import TestClient

from copia import service
from copia.providers.data.llm import ProviderError
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app, router
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage


def test_failed_summarization_error_is_sanitized_in_session_json_and_get_response(
    monkeypatch, tmp_path
):
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)

    def complete(messages, config):
        if config.model == "summary-model":
            raise ProviderError(
                "Alice's trip failed: authorization=Bearer summary-secret",
                status_code=503,
            )
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={
            "config": {
                "name": "Copia",
                "provider": "openai",
                "model": "main-model",
                "context_management": {
                    "recent_exchange_limit": 1,
                    "summary_batch_exchange_count": 1,
                    "summarizer": {"model": "summary-model"},
                },
            }
        },
    )
    session = sessions.load(created.json()["id"])
    assert session is not None
    session.messages = [
        ChatMessage(role="user", content="old"),
        ChatMessage(role="assistant", content="answer"),
        ChatMessage(role="user", content="recent"),
        ChatMessage(role="assistant", content="reply"),
    ]
    sessions.save(session)

    response = client.post(f"/sessions/{session.id}/messages", json={"content": "new question"})

    assert response.status_code == 502
    error = sessions.load(session.id).context.events[-1].error  # type: ignore[union-attr]
    assert error is not None
    assert "Alice's trip failed" in error
    assert "summary-secret" not in error
    assert "[REDACTED]" in error
    assert client.get(f"/sessions/{session.id}").json()["context"]["events"][-1]["error"] == error
    assert "summary-secret" not in (tmp_path / "sessions" / session.id / "session.json").read_text()


def test_failed_facts_error_is_sanitized_in_session_json_and_get_response(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)

    def complete(messages, config):
        if config.structured_output is not None:
            raise ProviderError(
                "Alice prefers concise facts: api_key=sk-facts-secret",
                status_code=503,
            )
        return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(router, "complete", complete)
    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={
            "config": {
                "name": "Copia",
                "provider": "openai",
                "model": "main-model",
                "context_management": {"strategy": "sticky_facts"},
            }
        },
    )
    session_id = created.json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "facts"})

    assert response.status_code == 502
    session = sessions.load(session_id)
    assert session is not None
    error = session.context.facts_events[-1].error
    assert error is not None
    assert "Alice prefers concise facts" in error
    assert "sk-facts-secret" not in error
    assert "[REDACTED]" in error
    assert (
        client.get(f"/sessions/{session_id}").json()["context"]["facts_events"][-1]["error"]
        == error
    )
    assert (
        "sk-facts-secret" not in (tmp_path / "sessions" / session_id / "session.json").read_text()
    )
