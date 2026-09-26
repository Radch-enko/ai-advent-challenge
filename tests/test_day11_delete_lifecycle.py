from datetime import UTC, datetime

from copia import service
from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.session_memory.data.pending_memory_repository import PendingMemoryRepository
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_session import ChatSession


def test_save_agent_state_does_not_resurrect_deleted_session(monkeypatch, tmp_path):
    root = tmp_path / "sessions"
    sessions = SessionsRepository(root)
    working = WorkingMemoryRepository(root)
    pending = PendingMemoryRepository(root)
    monkeypatch.setattr(service, "sessions", sessions)
    monkeypatch.setattr(service, "working_memory", working)
    monkeypatch.setattr(service, "pending_memory_repository", pending)

    now = datetime.now(UTC)
    session = ChatSession(
        id="deleted-session",
        config=AgentConfig(name="test", provider="openai", model="model"),
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    sessions.delete(session.id)

    _save_agent_state = service._save_agent_state
    _save_agent_state(session, Agent(session.config, object()))  # type: ignore[arg-type]

    assert sessions.load(session.id) is None
    assert not (root / session.id).exists()
