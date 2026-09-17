import json
from datetime import UTC, datetime

import pytest

from copia.data.providers.llm import ProviderError
from copia.data.working_memory_repository import WorkingMemoryRepository
from copia.domain.models.agent import Agent
from copia.domain.models.config import AgentConfig, ChatMessage, LLMResponse
from copia.domain.models.memory import WorkingMemoryItem
from copia.domain.services.memory_classifier import LLMMemoryClassifier


def working_item(value: str = "old") -> WorkingMemoryItem:
    now = datetime.now(UTC)
    return WorkingMemoryItem(id="item", key="goal", value=value, created_at=now, updated_at=now)


@pytest.mark.parametrize(
    "failure",
    [
        ProviderError("provider failed", response_body={"secret": "raw"}),
        TimeoutError("provider timed out"),
        ValueError("malformed structured output"),
    ],
)
def test_structured_memory_classifier_falls_back_to_noop(failure) -> None:
    class FailingRouter:
        def complete(self, messages, config):
            raise failure

    classifier = LLMMemoryClassifier(
        FailingRouter(), AgentConfig(name="test", provider="openai", model="test")
    )

    assert classifier.classify("message", [], [working_item()]) == []
    assert classifier.last_error is not None
    assert classifier.last_error.startswith(
        f"Memory classification failed at provider request: {type(failure).__name__}:"
    )
    assert classifier.last_error.endswith("; working memory was unchanged")


def test_structured_memory_classifier_serializes_existing_working_memory() -> None:
    class Router:
        calls = 0

        def complete(self, messages, config):
            self.calls += 1
            payload = json.loads(messages[-1].content)
            assert payload["working_memory"][0]["key"] == "goal"
            assert isinstance(payload["working_memory"][0]["created_at"], str)
            return LLMResponse(
                content='{"candidates": []}',
                provider=config.provider,
                model=config.model,
                structured_data={"candidates": []},
            )

    router = Router()
    classifier = LLMMemoryClassifier(
        router, AgentConfig(name="test", provider="openai", model="test")
    )

    assert classifier.classify("message", [], [working_item()]) == []
    assert router.calls == 1
    assert classifier.last_error is None


def test_structured_memory_classifier_rejects_malformed_schema_output() -> None:
    class MalformedRouter:
        def complete(self, messages, config):
            return LLMResponse(
                content="{}", provider=config.provider, model=config.model, structured_data={}
            )

    classifier = LLMMemoryClassifier(
        MalformedRouter(), AgentConfig(name="test", provider="openai", model="test")
    )

    assert classifier.classify("message", [], [working_item()]) == []
    assert classifier.last_error is not None


def test_classifier_failure_keeps_working_memory_and_allows_primary_response(tmp_path) -> None:
    repository = WorkingMemoryRepository(tmp_path)
    existing = [working_item()]

    class Router:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages: list[ChatMessage], config):
            self.calls += 1
            if config.structured_output is not None:
                raise ProviderError("classifier failed", response_body={"secret": "raw"})
            return LLMResponse(
                content="primary reply", provider=config.provider, model=config.model
            )

    router = Router()
    classifier = LLMMemoryClassifier(
        router, AgentConfig(name="test", provider="openai", model="test")
    )
    repository.save("session", existing)
    agent = Agent(
        AgentConfig(name="test", provider="openai", model="test"),
        router,  # type: ignore[arg-type]
        working_memory=existing,
        working_memory_store=repository,
        session_id="session",
        memory_classifier=classifier,
    )

    response = agent.ask("message")

    assert response.content == "primary reply"
    assert agent.working_memory == existing
    assert repository.load("session") == existing
    assert agent.memory_events[-1].message == (
        "Memory classification failed at provider request: ProviderError: classifier failed; "
        "working memory was unchanged"
    )


def test_working_memory_atomic_failure_preserves_files_and_automatic_undo(
    monkeypatch, tmp_path
) -> None:
    repository = WorkingMemoryRepository(tmp_path)
    before = [working_item()]
    after = [working_item("new")]
    repository.save("session", before)

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr("copia.data.working_memory_repository.os.replace", fail_replace)
    with pytest.raises(OSError):
        repository.save_automatic("session", before, after)

    assert repository.load("session") == before
    assert list((tmp_path / "session").glob(".working-*.tmp")) == []

    monkeypatch.undo()
    repository.save_automatic("session", before, after)
    assert repository.load("session") == after
    assert repository.undo_last("session") == before
    assert repository.load("session") == before
