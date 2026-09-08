from __future__ import annotations

from typing import Protocol

from .config import AgentConfig, ChatMessage, LLMResponse
from ..services.router import LLMRouter


class ProfilesSource(Protocol):
    def load(self) -> dict[str, AgentConfig]: ...


class Agent:
    """A stateful conversation with one configuration and in-memory history."""

    def __init__(self, config: AgentConfig, router: LLMRouter) -> None:
        self.config = config
        self._router = router
        self._history: list[ChatMessage] = []

    @property
    def history(self) -> list[ChatMessage]:
        return list(self._history)

    def ask(self, content: str) -> LLMResponse:
        message = ChatMessage(role="user", content=content)
        self._history.append(message)
        messages = self._messages_for_request()
        try:
            response = self._router.complete(messages, self.config)
        except Exception:
            self._history.pop()
            raise
        self._history.append(ChatMessage(role="assistant", content=response.content))
        return response

    def _messages_for_request(self) -> list[ChatMessage]:
        if self.config.system_prompt:
            return [ChatMessage(role="system", content=self.config.system_prompt), *self._history]
        return list(self._history)


class AgentFactory:
    def __init__(self, router: LLMRouter, profiles_repository: ProfilesSource) -> None:
        self._router = router
        self._profiles_repository = profiles_repository

    def profiles(self) -> dict[str, AgentConfig]:
        return self._profiles_repository.load()

    def create(self, config: AgentConfig) -> Agent:
        return Agent(config=config, router=self._router)

    def create_from_profile(self, profile_name: str) -> Agent:
        profiles = self.profiles()
        try:
            return self.create(profiles[profile_name])
        except KeyError as error:
            raise KeyError(f"Unknown profile: {profile_name}") from error
