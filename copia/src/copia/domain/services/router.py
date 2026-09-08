from __future__ import annotations

from dotenv import load_dotenv

from ..models.config import ChatMessage, LLMConfig, LLMResponse, ProviderCapabilities, ProviderModel, ProviderName
from ...data.providers.llm import GigaChatProvider, LLMProvider, OpenAIProvider, ProviderError


class LLMRouter:
    """Routes a provider-agnostic request to the configured LLM provider."""

    def __init__(self, providers: dict[ProviderName, LLMProvider] | None = None) -> None:
        load_dotenv()
        self._providers = providers or {
            ProviderName.OPENAI: OpenAIProvider(),
            ProviderName.GIGACHAT: GigaChatProvider(),
        }

    def complete(self, messages: list[ChatMessage], config: LLMConfig) -> LLMResponse:
        try:
            provider = self._providers[config.provider]
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {config.provider.value}") from error
        return provider.complete(messages, config)

    def capabilities(self, provider_name: ProviderName) -> ProviderCapabilities:
        try:
            return self._providers[provider_name].capabilities
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {provider_name.value}") from error

    def models(self, provider_name: ProviderName) -> list[ProviderModel]:
        try:
            return self._providers[provider_name].list_models()
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {provider_name.value}") from error
