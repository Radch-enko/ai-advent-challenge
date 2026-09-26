from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event, Lock

from fastapi.testclient import TestClient

from copia import service
from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession


class _ObservedLock:
    def __init__(self) -> None:
        self._lock = Lock()
        self.acquire_count = 0
        self.second_acquire_called = Event()

    def acquire(self) -> bool:
        self.acquire_count += 1
        if self.acquire_count == 2:
            self.second_acquire_called.set()
        return self._lock.acquire()

    def release(self) -> None:
        self._lock.release()


def test_concurrent_send_and_long_term_memory_toggle_are_serialized(monkeypatch, tmp_path):
    sessions_root = tmp_path / "sessions"
    sessions = SessionsRepository(sessions_root)
    profile_memory = ProfileMemoryRepository(tmp_path / "memory")
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "profile_memory", profile_memory)
    monkeypatch.setattr(service, "working_memory", WorkingMemoryRepository(sessions_root))
    monkeypatch.setattr(
        service, "pending_memory_repository", PendingMemoryRepository(sessions_root)
    )

    now = datetime.now(UTC)
    session = ChatSession(
        id="toggle-race",
        profile_name="test-profile",
        long_term_memory_enabled=True,
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    profile_memory.create(
        session.profile_name,
        LongTermMemoryItem(
            id="private-fact",
            category="profile",
            key="private-key",
            value="private-value",
            created_at=now,
            updated_at=now,
        ),
    )

    message_lock = _ObservedLock()
    monkeypatch.setattr(service, "session_message_locks", {session.id: message_lock})
    provider_started = Event()
    release_provider = Event()
    provider_requests: list[list[str]] = []

    def complete(messages, config):
        provider_requests.append([message.content for message in messages])
        if messages[-1].content == "first":
            provider_started.set()
            assert release_provider.wait(timeout=5)
        return LLMResponse(
            content=f"reply-{messages[-1].content}", provider="openai", model="model"
        )

    monkeypatch.setattr(service.router, "complete", complete)
    client = TestClient(app)

    with ThreadPoolExecutor(max_workers=2) as executor:
        send = executor.submit(
            client.post, f"/sessions/{session.id}/messages", json={"content": "first"}
        )
        assert provider_started.wait(timeout=5)
        toggle = executor.submit(
            client.patch, f"/sessions/{session.id}/long-term-memory", json={"enabled": False}
        )

        release_provider.set()
        # The toggle must acquire the same per-session lock before it can save
        # the new value. The old implementation never made this acquisition.
        assert message_lock.second_acquire_called.wait(timeout=5)
        assert send.result(timeout=5).status_code == 200
        assert toggle.result(timeout=5).status_code == 200

    restored = sessions.load(session.id)
    assert restored is not None
    assert restored.long_term_memory_enabled is False

    next_response = client.post(f"/sessions/{session.id}/messages", json={"content": "next"})
    assert next_response.status_code == 200
    assert not any("<long_term_memory>" in content for content in provider_requests[-1])
