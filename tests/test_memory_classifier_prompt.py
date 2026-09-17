import json

from copia.domain.models.config import AgentConfig, LLMResponse
from copia.domain.services.memory_classifier import (
    MEMORY_CLASSIFIER_SYSTEM_PROMPT,
    LLMMemoryClassifier,
)


def test_memory_classifier_prompt_defines_scope_boundaries_and_examples() -> None:
    captured: dict[str, str] = {}

    class Router:
        def complete(self, messages, config):
            captured["system"] = messages[0].content
            captured["payload"] = messages[1].content
            return LLMResponse(
                content='{"candidates": []}',
                provider=config.provider,
                model=config.model,
                structured_data={"candidates": []},
            )

    classifier = LLMMemoryClassifier(
        Router(), AgentConfig(name="test", provider="openai", model="test")
    )

    assert classifier.classify("message", [], []) == []
    assert captured["system"] == MEMORY_CLASSIFIER_SYSTEM_PROMPT
    assert "working: temporary context for the current chat or task" in captured["system"]
    assert (
        "long_term: stable user information that should be useful in future chats"
        in captured["system"]
    )
    assert '"Always answer briefly and perform a self-check" -> long_term' in captured["system"]
    assert json.loads(captured["payload"])["message"] == "message"
