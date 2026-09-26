from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event, Lock, Thread

from fastapi.testclient import TestClient

from copia import service
from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.service import app
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.models.pending_memory_suggestion import PendingMemorySuggestion
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession
from copia.sessions.domain.models.context_management_config import ContextManagementConfig
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.models.summarization_event import SummarizationEvent


def _failed_session(session_id: str) -> ChatSession:
    now = datetime.now(UTC)
    return ChatSession(
        id=session_id,
        config=AgentConfig(
            name="test",
            provider="openai",
            model="main-model",
            context_management=ContextManagementConfig(
                recent_exchange_limit=1,
                summary_batch_exchange_count=1,
                summarizer={"provider": "openai", "model": "summary-model", "prompt": "summarize"},
            ),
        ),
        messages=[
            ChatMessage(role="user", content="old user"),
            ChatMessage(role="assistant", content="old answer"),
            ChatMessage(role="user", content="pending user"),
        ],
        context=ConversationContext(
            events=[
                SummarizationEvent(
                    id="failed-event",
                    status="failed",
                    after_message_index=2,
                    start_message_index=0,
                    message_count=2,
                    provider="openai",
                    model="summary-model",
                    duration_seconds=0,
                    created_at=now,
                    updated_at=now,
                )
            ]
        ),
        created_at=now,
        updated_at=now,
    )


def _memory(
    session_id: str, pending: PendingMemoryRepository, working: WorkingMemoryRepository
) -> None:
    now = datetime.now(UTC)
    working.save(
        session_id,
        [WorkingMemoryItem(id="working", key="goal", value="keep", created_at=now, updated_at=now)],
    )
    pending.save(
        session_id,
        [
            PendingMemorySuggestion(
                id="pending",
                candidate=MemoryCandidate(
                    scope="long_term",
                    action="create",
                    category="profile",
                    key="preference",
                    value="dark mode",
                    confidence=1,
                    reason="regression",
                ),
                created_at=now,
            )
        ],
    )


def test_retry_and_send_are_serialized_without_losing_session_state(monkeypatch, tmp_path):
    root = tmp_path / "sessions"
    sessions = SessionsRepository(root)
    pending = PendingMemoryRepository(root)
    working = WorkingMemoryRepository(root)
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    monkeypatch.setattr(service, "working_memory", working)
    session = _failed_session("retry-concurrent")
    sessions.save(session)
    _memory(session.id, pending, working)

    summary_started = Event()
    release_summary = Event()
    send_loaded_during_retry = Event()
    load_lock = Lock()
    original_load = sessions.load

    def load(session_id):
        result = original_load(session_id)
        with load_lock:
            if summary_started.is_set() and not release_summary.is_set():
                send_loaded_during_retry.set()
        return result

    monkeypatch.setattr(sessions, "load", load)

    def complete(messages, config):
        if config.model == "summary-model":
            summary_started.set()
            assert release_summary.wait(timeout=5)
            return LLMResponse(content="summary", provider="openai", model="summary-model")
        return LLMResponse(content="reply", provider="openai", model="main-model")

    monkeypatch.setattr(service.router, "complete", complete)
    client = TestClient(app)

    with ThreadPoolExecutor(max_workers=2) as executor:
        retry = executor.submit(client.post, f"/sessions/{session.id}/summarization/retry")
        assert summary_started.wait(timeout=5)
        send = executor.submit(
            client.post, f"/sessions/{session.id}/messages", json={"content": "new message"}
        )
        assert not send_loaded_during_retry.wait(timeout=0.2)
        release_summary.set()
        retry_response = retry.result(timeout=5)
        send_response = send.result(timeout=5)

    assert retry_response.status_code == 200
    assert send_response.status_code == 200
    restored = sessions.load(session.id)
    assert restored is not None
    assert [message.content for message in restored.messages] == [
        "old user",
        "old answer",
        "pending user",
        "reply",
        "new message",
        "reply",
    ]
    assert [item.key for item in working.load(session.id)] == ["goal"]
    assert [item.id for item in pending.load(session.id)] == ["pending"]


def test_retry_cannot_resurrect_session_deleted_during_save(monkeypatch, tmp_path):
    root = tmp_path / "sessions"
    sessions = SessionsRepository(root)
    pending = PendingMemoryRepository(root)
    working = WorkingMemoryRepository(root)
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "pending_memory_repository", pending)
    monkeypatch.setattr(service, "working_memory", working)
    session = _failed_session("retry-delete")
    sessions.save(session)
    _memory(session.id, pending, working)

    monkeypatch.setattr(
        service.router,
        "complete",
        lambda messages, config: LLMResponse(
            content="summary", provider="openai", model=config.model
        ),
    )
    delete_started = Event()
    delete_finished = Event()
    delete_thread: Thread | None = None
    original_save = sessions.save

    def save(value):
        nonlocal delete_thread
        if value.id == session.id and not delete_started.is_set():
            delete_started.set()
            delete_thread = Thread(
                target=lambda: (service.delete_session(session.id), delete_finished.set())
            )
            delete_thread.start()
            assert delete_started.is_set()
            original_save(value)
        else:
            original_save(value)

    monkeypatch.setattr(sessions, "save", save)
    response = TestClient(app).post(f"/sessions/{session.id}/summarization/retry")

    assert response.status_code == 200
    assert delete_finished.wait(timeout=5)
    assert delete_thread is not None
    assert sessions.load(session.id) is None
    assert not (root / session.id).exists()
