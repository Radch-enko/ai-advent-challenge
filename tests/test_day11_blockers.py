from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import _save_agent_state, app
from copia.data.pending_memory_repository import PendingMemoryRepository
from copia.data.profile_memory_repository import ProfileMemoryRepository
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.models.memory import MemoryCandidate, PendingMemorySuggestion
from copia.domain.services.memory_policy import HybridMemoryPolicy


def test_repository_identifiers_reject_traversal_and_noncanonical_values(tmp_path):
    sessions = SessionsRepository(tmp_path)
    working = WorkingMemoryRepository(tmp_path)
    pending = PendingMemoryRepository(tmp_path)
    profile = ProfileMemoryRepository(tmp_path)
    for operation in (
        lambda: sessions.load("../escape"),
        lambda: sessions.load_branch("valid", "a/b"),
        lambda: working.load("."),
        lambda: pending.load("C:\\escape"),
        lambda: profile.load("../profile"),
    ):
        with pytest.raises(ValueError):
            operation()


def test_pending_suggestions_survive_later_working_classification(tmp_path):
    store = WorkingMemoryRepository(tmp_path)
    first = MemoryCandidate(
        scope="long_term",
        action="create",
        category="profile",
        key="language",
        value="Russian",
        confidence=1,
        reason="test",
    )
    _, pending, _ = HybridMemoryPolicy().apply("session", [first], store)
    second = MemoryCandidate(
        scope="working", action="create", key="goal", value="Ship", confidence=1, reason="test"
    )
    items, retained, _ = HybridMemoryPolicy().apply("session", [second], store, pending)
    assert items[0].key == "goal"
    assert retained == pending


def test_save_agent_state_preserves_automatic_undo_snapshot(tmp_path, monkeypatch):
    sessions = SessionsRepository(tmp_path / "sessions")
    working = WorkingMemoryRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "working_memory", working)
    now = datetime.now(UTC)
    session = service.ChatSession(
        id="session",
        config=AgentConfig(name="x", provider="openai", model="m"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    before = service.WorkingMemoryItem(
        id="one", key="goal", value="old", created_at=now, updated_at=now
    )
    after = before.model_copy(update={"value": "new"})
    working.save_automatic(session.id, [before], [after])
    agent = Agent(session.config, _Router(), working_memory=[after])
    _save_agent_state(session, agent)
    assert working.undo_last(session.id) == [before]


def test_working_update_returns_memory_events_and_api_rejects_bad_session(tmp_path, monkeypatch):
    sessions = SessionsRepository(tmp_path / "sessions")
    working = WorkingMemoryRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "working_memory", working)
    now = datetime.now(UTC)
    session = service.ChatSession(
        id="session",
        config=AgentConfig(name="x", provider="openai", model="m"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    item = service.WorkingMemoryItem(
        id="one", key="goal", value="old", created_at=now, updated_at=now
    )
    working.save(session.id, [item])
    response = TestClient(app).patch("/sessions/session/working-memory/one", json={"value": "new"})
    assert response.status_code == 200
    assert response.json()["memory_events"][0]["action"] == "updated"
    assert TestClient(app).get("/sessions/../escape").status_code in {404, 422}


def test_approval_does_not_reinterpret_stale_update_as_create(tmp_path, monkeypatch):
    sessions = SessionsRepository(tmp_path / "sessions")
    profiles = ProfileMemoryRepository(tmp_path / "profile")
    pending = PendingMemoryRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "profile_memory", profiles)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    client = TestClient(app)
    session_id = client.post("/sessions", json={"profile_name": "planner"}).json()["id"]
    now = datetime.now(UTC)
    candidate = MemoryCandidate(
        scope="long_term",
        action="update",
        category="profile",
        key="x",
        value="new",
        target_id="missing",
        confidence=1,
        reason="test",
    )
    pending.save(
        session_id, [PendingMemorySuggestion(id="candidate", candidate=candidate, created_at=now)]
    )
    response = client.post(f"/sessions/{session_id}/memory/pending/candidate/approve")
    assert response.status_code == 404
    assert profiles.load("planner") == []
    assert pending.load(session_id)


class _Router:
    def complete(self, messages, config):
        return LLMResponse(content="ok", provider=config.provider, model=config.model)
