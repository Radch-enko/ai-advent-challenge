import threading
from datetime import UTC, datetime

from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.api.deletion_routes import SessionDeletionRoutes
from copia.sessions.api.session_access import SessionAccess
from copia.sessions.api.session_access_runtime import SessionAccessRuntime
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession


def test_delete_returns_while_conversation_holds_session_lock(tmp_path) -> None:
    repository = SessionsRepository(tmp_path / "sessions")
    working = WorkingMemoryRepository(tmp_path / "sessions")
    pending = PendingMemoryRepository(tmp_path / "sessions")
    now = datetime.now(UTC)
    session = ChatSession(
        id="session",
        config={"name": "Agent", "provider": "openai", "model": "model"},
        created_at=now,
        updated_at=now,
    )
    repository.save(session)

    locks = {}
    lifecycle_lock = threading.RLock()
    access_runtime = SessionAccessRuntime(
        sessions=repository,
        threadpool=lambda *_args: None,
        lifecycle_lock=lifecycle_lock,
        message_locks=locks,
    )
    access = SessionAccess(lambda: access_runtime)
    lock_state = access.session_message_lock(session.id)
    lock_state.lock.acquire()

    routes = SessionDeletionRoutes(
        get_repository=lambda: repository,
        delete_working_memory=working.delete,
        delete_pending_memory=pending.delete,
        get_pending_cache=dict,
        get_approved_cache=dict,
        acquire_message_lock=access.session_message_lock,
        release_message_lock=access.release_session_message_lock,
        get_lifecycle_lock=lambda: lifecycle_lock,
    )

    routes.delete_session(session.id)

    assert repository.load(session.id) is None
    assert lock_state.retired
    assert lock_state.users == 1
    assert lock_state.on_idle

    working.save(session.id, [])
    pending.save(session.id, [])
    lock_state.lock.release()
    access.release_session_message_lock(lock_state)

    assert not lock_state.on_idle
    assert working.load(session.id) == []
    assert pending.load(session.id) == []
    assert not (tmp_path / "sessions" / session.id / "working_memory.json").exists()
    assert not (tmp_path / "sessions" / session.id / "pending_memory.json").exists()
    assert session.id not in locks
