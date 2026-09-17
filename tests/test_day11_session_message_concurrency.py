from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event, Lock

from fastapi.testclient import TestClient

from copia.api import service
from copia.api.service import app
from copia.data.pending_memory_repository import PendingMemoryRepository
from copia.data.profile_memory_repository import ProfileMemoryRepository
from copia.data.sessions_repository import SessionsRepository
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.models.memory import MemoryCandidate
from copia.domain.models.session import ChatSession


def test_concurrent_messages_preserve_transcript_and_pending_memory(monkeypatch, tmp_path):
    root = tmp_path / "sessions"
    sessions = SessionsRepository(root)
    pending = PendingMemoryRepository(root)
    working = WorkingMemoryRepository(root)
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    monkeypatch.setattr(service, "working_memory", working)
    monkeypatch.setattr(service, "profile_memory", ProfileMemoryRepository(tmp_path / "memory"))

    now = datetime.now(UTC)
    session = ChatSession(
        id="concurrent-session",
        title="Concurrent test",
        profile_name="test-profile",
        long_term_memory_enabled=True,
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)

    first_provider_started = Event()
    release_first_provider = Event()
    second_load_seen = Event()
    load_lock = Lock()
    load_count = 0
    original_load = sessions.load

    def load(session_id):
        nonlocal load_count
        result = original_load(session_id)
        with load_lock:
            load_count += 1
            if first_provider_started.is_set() and load_count >= 3:
                second_load_seen.set()
        return result

    monkeypatch.setattr(sessions, "load", load)

    class Classifier:
        last_error = None

        def classify(self, content, *_args):
            return [
                MemoryCandidate(
                    scope="working",
                    action="create",
                    key=f"working-{content}",
                    value=f"value-{content}",
                    confidence=1,
                    reason="concurrency regression",
                ),
                MemoryCandidate(
                    scope="long_term",
                    action="create",
                    category="knowledge",
                    key=f"key-{content}",
                    value=f"value-{content}",
                    confidence=1,
                    reason="concurrency regression",
                ),
            ]

    monkeypatch.setattr(service, "LLMMemoryClassifier", lambda *_args: Classifier())

    def complete(messages, config):
        content = messages[-1].content
        if content == "first":
            first_provider_started.set()
            assert release_first_provider.wait(timeout=5)
        return LLMResponse(content=f"reply-{content}", provider="openai", model="model")

    monkeypatch.setattr(service.router, "complete", complete)
    client = TestClient(app)

    def send(content):
        return client.post(f"/sessions/{session.id}/messages", json={"content": content})

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(send, "first")
        assert first_provider_started.wait(timeout=5)
        second = executor.submit(send, "second")
        # With the old split locking, this observes the second request reading stale state.
        second_load_seen.wait(timeout=1)
        release_first_provider.set()
        responses = [first.result(timeout=5), second.result(timeout=5)]

    assert all(response.status_code == 200 for response in responses)
    restored = sessions.load(session.id)
    assert restored is not None
    assert [message.content for message in restored.messages] == [
        "first",
        "reply-first",
        "second",
        "reply-second",
    ]
    assert {item.candidate.key for item in pending.load(session.id)} == {
        "key-first",
        "key-second",
    }
    assert {item.key for item in working.load(session.id)} == {"working-first", "working-second"}
