import json

from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.domain.services.llm_memory_classifier import LLMMemoryClassifier
from copia.session_memory.domain.services.memory_classifier_prompt import (
    MEMORY_CLASSIFIER_SYSTEM_PROMPT,
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
    assert "working: временный контекст текущего чата или задачи" in captured["system"]
    assert (
        "long_term: устойчивые сведения о пользователе, которые пригодятся в будущих чатах"
        in captured["system"]
    )
    assert "«Всегда отвечай кратко и проверяй свой ответ» → `long_term`" in captured["system"]
    assert json.loads(captured["payload"])["message"] == "message"
