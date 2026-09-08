from pathlib import Path

from copia.domain.models.agent import Agent, AgentFactory
from copia.domain.models.config import AgentConfig, LLMResponse, ProviderName
from copia.domain.services.router import LLMRouter


class FakeRouter:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, messages, config):
        self.requests.append((messages, config))
        return LLMResponse(content=f"answer: {messages[-1].content}", provider=config.provider, model=config.model)


def config(name: str = "test") -> AgentConfig:
    return AgentConfig(name=name, provider="openai", model="test-model", system_prompt="system")


def test_agents_keep_independent_history() -> None:
    router = FakeRouter()
    first = Agent(config("first"), router)  # type: ignore[arg-type]
    second = Agent(config("second"), router)  # type: ignore[arg-type]

    first.ask("first message")
    second.ask("second message")

    assert [message.content for message in first.history] == ["first message", "answer: first message"]
    assert [message.content for message in second.history] == ["second message", "answer: second message"]
    assert [message.content for message in router.requests[0][0]] == ["system", "first message"]


def test_factory_loads_profiles(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles.json"
    profiles.write_text('{"writer": {"name": "writer", "provider": "openai", "model": "test"}}')
    from copia.data.profiles_repository import ProfilesRepository

    factory = AgentFactory(FakeRouter(), ProfilesRepository(profiles))  # type: ignore[arg-type]

    agent = factory.create_from_profile("writer")

    assert agent.config.name == "writer"
    assert agent.config.provider is ProviderName.OPENAI
