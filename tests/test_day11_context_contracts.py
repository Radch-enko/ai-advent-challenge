from datetime import UTC, datetime

from copia.agents.domain.models.agent_config import AgentConfig
from copia.profile_memory.data.profile_memory_repository import ProfileMemoryRepository
from copia.profile_memory.domain.contracts.long_term_memory_store import LongTermMemoryStore
from copia.profile_memory.domain.models.long_term_memory_item import LongTermMemoryItem
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.contracts.working_memory_store import WorkingMemoryStore
from copia.session_memory.domain.models.working_memory_item import WorkingMemoryItem
from copia.sessions.data.sessions_repository import SessionsRepository
from copia.sessions.domain.contracts.short_term_transcript_store import ShortTermTranscriptStore
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.sessions.domain.services.context_strategy import context_strategy_for


def _long(key: str, value: str) -> LongTermMemoryItem:
    now = datetime.now(UTC)
    return LongTermMemoryItem(
        id=key, category="profile", key=key, value=value, created_at=now, updated_at=now
    )


def _working(key: str, value: str) -> WorkingMemoryItem:
    now = datetime.now(UTC)
    return WorkingMemoryItem(id=key, key=key, value=value, created_at=now, updated_at=now)


def test_data_repositories_satisfy_provider_agnostic_memory_contracts(tmp_path):
    assert isinstance(SessionsRepository(tmp_path / "sessions"), ShortTermTranscriptStore)
    assert isinstance(WorkingMemoryRepository(tmp_path / "sessions"), WorkingMemoryStore)
    assert isinstance(ProfileMemoryRepository(tmp_path / "profiles"), LongTermMemoryStore)


def test_context_conflicts_are_resolved_short_term_then_working_then_long_term():
    config = AgentConfig(name="test", provider="openai", model="model")
    strategy = context_strategy_for(
        config,
        long_term_memory=[_long("goal", "long"), _long("theme", "long-theme")],
        working_memory=[_working("goal", "working"), _working("theme", "working-theme")],
    )

    request = strategy.messages_for_request(
        [ChatMessage(role="user", content="goal: short")], ConversationContext()
    )

    assert "short" in request[-1].content
    assert '"value": "working"' not in request[0].content
    assert '"value": "long"' not in request[0].content
    assert "working-theme" in request[0].content
    assert "long-theme" not in request[0].content


def test_context_budget_evicts_long_term_before_working_but_keeps_dialogue():
    config = AgentConfig(
        name="test", provider="openai", model="model", generation={"max_output_tokens": 1}
    )
    strategy = context_strategy_for(
        config,
        long_term_memory=[_long("old", "l" * 300)],
        working_memory=[_working("current", "w" * 100)],
        context_window=180,
    )

    request = strategy.messages_for_request(
        [ChatMessage(role="user", content="keep this short-term dialogue")], ConversationContext()
    )

    assert request[-1].content == "keep this short-term dialogue"
    assert "current" in request[0].content
    assert "old" not in request[0].content
