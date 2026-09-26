from datetime import UTC, datetime

from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.chat_session import ChatSession


class FakeRouter:
    def complete(self, messages, config):
        return LLMResponse(content="reply", provider=config.provider, model=config.model)


def test_agent_persists_timestamps_for_user_and_assistant_messages() -> None:
    config = AgentConfig(name="Copia", provider="openai", model="model")
    agent = Agent(config, FakeRouter())  # type: ignore[arg-type]

    before = datetime.now(UTC)
    agent.ask("hello")
    after = datetime.now(UTC)

    assert len(agent.history) == 2
    user_created_at = agent.history[0].created_at
    assistant_created_at = agent.history[1].created_at
    assert user_created_at is not None
    assert assistant_created_at is not None
    assert before <= user_created_at <= after
    assert before <= assistant_created_at <= after


def test_session_repository_round_trips_message_timestamp(tmp_path) -> None:
    created_at = datetime(2026, 9, 17, 8, 7, 6, tzinfo=UTC)
    session = ChatSession(
        id="session",
        config=AgentConfig(name="Copia", provider="openai", model="model"),
        messages=[ChatMessage(role="user", content="hello", created_at=created_at)],
        created_at=created_at,
        updated_at=created_at,
    )
    repository = SessionsRepository(tmp_path / "sessions")
    repository.save(session)

    restored = repository.load("session")

    assert restored is not None
    assert restored.messages[0].created_at == created_at
