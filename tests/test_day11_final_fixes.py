from datetime import UTC, datetime
from threading import Event, Thread

import pytest

from copia.api import service
from copia.data.pending_memory_repository import PendingMemoryRepository
from copia.data.profile_memory_repository import ProfileMemoryRepository
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.config import AgentConfig
from copia.domain.models.memory import MemoryCandidate, PendingMemorySuggestion
from copia.domain.models.session import ChatSession


def test_automatic_classification_cannot_interleave_with_delete(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    working = WorkingMemoryRepository(tmp_path / "sessions")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "working_memory", working)
    session = ChatSession(
        id="session",
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    sessions.save(session)
    save_started = Event()
    delete_finished = Event()
    delete_attempted = Event()
    original_save = working.save_automatic

    def save_automatic(*args):
        save_started.set()

        def delete():
            delete_attempted.set()
            service.delete_session(session.id)
            delete_finished.set()

        delete_thread = Thread(target=delete)
        delete_thread.start()
        assert delete_attempted.wait(timeout=1)
        assert delete_thread.is_alive()
        original_save(*args)

    monkeypatch.setattr(working, "save_automatic", save_automatic)

    class Agent:
        def ask(self, content):
            item = service.WorkingMemoryItem(
                id="item",
                key="goal",
                value=content,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            working.save_automatic(session.id, [], [item])
            assert save_started.is_set()
            return service.LLMResponse(content="ok", provider="openai", model="model")

    assert service._ask_agent(session.id, Agent(), "classified")
    # The delete started while the lifecycle lock was held and completes after ask returns.
    assert delete_finished.wait(timeout=1)
    assert sessions.load(session.id) is None
    assert not (tmp_path / "sessions" / session.id).exists()


def test_rejecting_same_candidate_is_idempotent(monkeypatch, tmp_path):
    sessions = SessionsRepository(tmp_path / "sessions")
    pending = PendingMemoryRepository(tmp_path / "sessions")
    profiles = ProfileMemoryRepository(tmp_path / "memory")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    monkeypatch.setattr(service, "profile_memory", profiles)
    session = ChatSession(
        id="session",
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    sessions.save(session)
    pending.save(
        session.id,
        [
            PendingMemorySuggestion(
                id="candidate",
                candidate=MemoryCandidate(
                    scope="long_term",
                    action="create",
                    category="profile",
                    key="preference",
                    value="dark mode",
                    confidence=1,
                    reason="test",
                ),
                created_at=datetime.now(UTC),
            )
        ],
    )

    first = service._reject_memory(session.id, "candidate")
    second = service._reject_memory(session.id, "candidate")

    assert first.memory_events[0].action == "rejected"
    assert second.memory_events == []
    assert pending.load(session.id) == []
    assert profiles.load("profile") == []


@pytest.mark.parametrize(
    ("repository", "save_args", "prefix"),
    [
        (PendingMemoryRepository, ("session", []), ".pending-"),
        (ProfileMemoryRepository, ("profile", []), ".memory-"),
    ],
)
def test_memory_repository_removes_temporary_file_when_replace_fails(
    monkeypatch, tmp_path, repository, save_args, prefix
):
    instance = repository(tmp_path)
    monkeypatch.setattr(
        f"copia.data.{('pending_memory' if prefix == '.pending-' else 'profile_memory')}_repository.os.replace",
        lambda source, target: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        instance.save(*save_args)

    assert list(tmp_path.rglob(f"{prefix}*.tmp")) == []
