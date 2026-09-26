from copia.agents.domain.models.agent import Agent
from copia.agents.domain.models.agent_config import AgentConfig
from copia.session_memory.data.working_memory_repository import WorkingMemoryRepository
from copia.session_memory.domain.models.memory_candidate import MemoryCandidate
from copia.session_memory.domain.services.deterministic_fake_memory_classifier import (
    DeterministicFakeMemoryClassifier,
)


def test_context_refresh_failure_keeps_applied_memory_and_records_error(monkeypatch, tmp_path):
    repository = WorkingMemoryRepository(tmp_path)
    candidate = MemoryCandidate(
        scope="working",
        action="create",
        key="goal",
        value="Ship",
        confidence=1,
        reason="explicit",
    )
    agent = Agent(
        AgentConfig(name="test", provider="openai", model="test"),
        object(),  # type: ignore[arg-type]
        working_memory_store=repository,
        session_id="session",
        memory_classifier=DeterministicFakeMemoryClassifier([candidate]),
    )

    def fail_context_refresh(*args, **kwargs):
        raise ValueError("context refresh failed")

    monkeypatch.setattr(
        "copia.agents.domain.models.agent.context_strategy_for", fail_context_refresh
    )

    agent._classify_memory("Remember this for this session")

    assert [item.value for item in agent.working_memory] == ["Ship"]
    assert [item.value for item in repository.load("session")] == ["Ship"]
    assert [event.action for event in agent.memory_events] == ["created", "error"]
    assert (
        agent.memory_events[-1].message
        == "Memory update failed: ValueError: context refresh failed"
    )
