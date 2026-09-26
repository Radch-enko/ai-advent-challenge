from datetime import UTC, datetime
from threading import RLock
from unittest.mock import Mock

from copia.agents.domain.models.agent_config import AgentConfig
from copia.invariants.data.invariants_repository import InvariantsRepository
from copia.providers.domain.models.llm_response import LLMResponse
from copia.sessions.application.session_title_generator import SessionTitleGenerator
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession


def test_generated_title_does_not_change_conversation_history(tmp_path):
    # Вход
    sessions = SessionsRepository(tmp_path / "sessions")
    messages = [
        ChatMessage(role="user", content="Помоги спланировать поездку"),
        ChatMessage(role="assistant", content="Куда вы хотите поехать?"),
    ]
    now = datetime.now(UTC)
    session = ChatSession(
        id="title-session",
        config=AgentConfig(name="test", provider="openai", model="model"),
        messages=messages,
        created_at=now,
        updated_at=now,
    )
    sessions.save(session)
    router = Mock()
    router.complete.return_value = LLMResponse(
        content="", provider="openai", model="model", structured_data={"title": "План поездки"}
    )
    lifecycle_lock = RLock()
    generator = SessionTitleGenerator(
        lambda: sessions,
        lambda: InvariantsRepository(tmp_path / "invariants.json"),
        lambda: router,
        lambda: lifecycle_lock,
    )

    # Действие
    generator.generate(session.id)

    # Результат
    saved = sessions.load(session.id)
    assert saved is not None
    assert saved.title == "План поездки"
    assert saved.messages == messages
    router.complete.assert_called_once()
