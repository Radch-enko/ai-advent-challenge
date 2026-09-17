from datetime import UTC, datetime

from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.pending_memory_repository import PendingMemoryRepository
from copia.data.profile_memory_repository import ProfileMemoryRepository
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.models.memory import (
    LongTermMemoryItem,
    MemoryCandidate,
    PendingMemorySuggestion,
    WorkingMemoryItem,
)
from copia.domain.services.memory_classifier import DeterministicFakeMemoryClassifier
from copia.domain.services.memory_policy import HybridMemoryPolicy


def test_classifier_failure_retains_message_and_working_memory(tmp_path):
    class FailingClassifier:
        def classify(self, *args, **kwargs):
            raise ValueError("provider payload must not be exposed")

    class ReplyRouter:
        def complete(self, messages, config):
            return LLMResponse(content="reply", provider=config.provider, model=config.model)

    repository = WorkingMemoryRepository(tmp_path)
    now = datetime.now(UTC)
    item = WorkingMemoryItem(id="one", key="goal", value="keep", created_at=now, updated_at=now)
    repository.save("session", [item])
    agent = Agent(
        AgentConfig(name="test", provider="openai", model="test-model"),
        ReplyRouter(),  # type: ignore[arg-type]
        working_memory=[item],
        working_memory_store=repository,
        session_id="session",
        memory_classifier=FailingClassifier(),  # type: ignore[arg-type]
    )

    agent.ask("accepted message")

    assert any(message.content == "accepted message" for message in agent.history)
    assert repository.load("session") == [item]
    assert agent.memory_events[-1].action == "error"
    assert agent.memory_events[-1].message == (
        "Memory update failed: ValueError: provider payload must not be exposed"
    )


def test_candidate_category_action_and_undo_are_preserved(tmp_path):
    repository = WorkingMemoryRepository(tmp_path)
    policy = HybridMemoryPolicy()
    created = MemoryCandidate(
        scope="working", action="create", key="goal", value="first", confidence=1, reason="explicit"
    )
    policy.apply("session", [created], repository)
    updated = MemoryCandidate(
        scope="working",
        action="update",
        key="goal",
        value="second",
        confidence=1,
        reason="explicit",
    )
    policy.apply("session", [updated], repository)
    assert repository.load("session")[0].value == "second"
    assert repository.undo_last("session")[0].value == "first"


def test_approve_supports_create_update_delete_without_early_profile_write(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    profile = ProfileMemoryRepository(tmp_path / "profile")
    pending = PendingMemoryRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "profile_memory", profile)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    client = TestClient(app)
    session_id = client.post("/sessions", json={"profile_name": "planner"}).json()["id"]
    now = datetime.now(UTC)
    existing = LongTermMemoryItem(
        id="existing", category="decision", key="plan", value="old", created_at=now, updated_at=now
    )
    profile.save("planner", [existing])

    def suggest(action, key, value, target_id=None):
        candidate = MemoryCandidate(
            scope="long_term",
            action=action,
            category="decision",
            key=key,
            value=value,
            target_id=target_id,
            confidence=1,
            reason="explicit",
        )
        pending.save(
            session_id, [PendingMemorySuggestion(id=action, candidate=candidate, created_at=now)]
        )
        if action == "create":
            assert not any(item.key == key for item in profile.load("planner"))
        return client.post(f"/sessions/{session_id}/memory/pending/{action}/approve")

    created = suggest("create", "new-plan", "new")
    assert created.status_code == 200
    assert created.json()["category"] == "decision"
    assert created.json()["memory_events"][0]["action"] == "approved"
    updated = suggest("update", "plan", "new", "existing")
    assert updated.json()["memory_events"][0]["action"] == "approved"
    deleted = suggest("delete", "plan", None, "existing")
    assert deleted.json()["memory_events"][0]["action"] == "approved"


def test_memory_classifier_fake_is_deterministic():
    candidate = MemoryCandidate(
        scope="long_term",
        action="create",
        category="knowledge",
        key="topic",
        value="value",
        confidence=1,
        reason="test",
    )
    assert DeterministicFakeMemoryClassifier([candidate]).classify("message", [], []) == [candidate]
