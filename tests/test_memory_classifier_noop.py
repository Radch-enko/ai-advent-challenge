from copia.agents.domain.models.agent_config import AgentConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.session_memory.domain.services.llm_memory_classifier import LLMMemoryClassifier


def test_classifier_ignores_empty_key_for_noop_candidate() -> None:
    class Router:
        def complete(self, messages, config):
            return LLMResponse(
                content="{}",
                provider=config.provider,
                model=config.model,
                structured_data={
                    "candidates": [
                        {
                            "scope": "none",
                            "action": "skip",
                            "category": None,
                            "key": "",
                            "value": None,
                            "target_id": None,
                            "confidence": 1,
                            "reason": "No memory needed",
                        }
                    ]
                },
            )

    classifier = LLMMemoryClassifier(
        Router(), AgentConfig(name="test", provider="openai", model="test")
    )

    assert classifier.classify("What time is it?", [], []) == []
    assert classifier.last_error is None
