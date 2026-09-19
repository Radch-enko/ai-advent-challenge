from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.providers.llm import ProviderError
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.models.memory import WorkingMemoryItem
from copia.domain.services.memory_classifier import LLMMemoryClassifier


def _working_memory() -> list[WorkingMemoryItem]:
    now = datetime.now(UTC)
    return [
        WorkingMemoryItem(
            id="item", key="goal", value="finish the report", created_at=now, updated_at=now
        )
    ]


@pytest.mark.parametrize(
    "message",
    [
        "Alice's trip failed: authorization=Bearer provider-secret",
        "Alice's trip failed: api_key=api-secret",
        "Alice's trip failed: token=eyJheader.payload.signature",
    ],
)
def test_memory_classifier_error_is_sanitized_before_memory_event(message: str, tmp_path) -> None:
    class FailingRouter:
        def complete(self, messages, config):
            raise ProviderError(message, status_code=503)

    classifier = LLMMemoryClassifier(
        FailingRouter(), AgentConfig(name="test", provider="openai", model="model")
    )
    working_memory_store = WorkingMemoryRepository(tmp_path)
    working_memory_store.save("session", _working_memory())
    agent = Agent(
        AgentConfig(name="test", provider="openai", model="model"),
        FailingRouter(),  # type: ignore[arg-type]
        working_memory=_working_memory(),
        working_memory_store=working_memory_store,
        session_id="session",
        memory_classifier=classifier,
    )

    agent._classify_memory("Alice's trip")

    event = agent.memory_events[-1]
    assert event.message is not None
    assert "Alice's trip failed" in event.message
    assert "[REDACTED]" in event.message
    assert "provider-secret" not in event.message
    assert "api-secret" not in event.message
    assert "eyJheader.payload.signature" not in event.message


def test_generic_memory_classifier_error_is_sanitized_and_api_safe(monkeypatch, tmp_path) -> None:
    sessions = SessionsRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)

    class FailingClassifier:
        last_error = None
        last_trace = None
        last_duration_seconds = None

        def classify(self, *args, **kwargs):
            raise ValueError("Alice's trip failed: authorization=Bearer generic-secret")

    class ReplyRouter:
        def complete(self, messages, config):
            return LLMResponse(content="reply", provider=config.provider, model=config.model)

    monkeypatch.setattr(service, "LLMMemoryClassifier", lambda *_args: FailingClassifier())
    monkeypatch.setattr(service, "router", ReplyRouter())
    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={"config": {"name": "Copia", "provider": "openai", "model": "model"}},
    )
    session_id = created.json()["id"]

    response = client.post(f"/sessions/{session_id}/messages", json={"content": "Alice's trip"})

    assert response.status_code == 200
    event = response.json()["memory_events"][-1]
    assert "Alice's trip failed" in event["message"]
    assert "[REDACTED]" in event["message"]
    assert "generic-secret" not in event["message"]
    persisted = (tmp_path / "sessions" / session_id / "session.json").read_text()
    assert "generic-secret" not in persisted
    session_response = client.get(f"/sessions/{session_id}")
    assert session_response.status_code == 200
    assert "generic-secret" not in session_response.text
