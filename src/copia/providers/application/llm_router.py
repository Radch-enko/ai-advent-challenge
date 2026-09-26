from __future__ import annotations

from dotenv import load_dotenv

from copia.agent_logs.domain.contracts.agent_log_sink import AgentLogSink
from copia.providers.data.llm import GigaChatProvider, LLMProvider, OpenAIProvider, ProviderError
from copia.providers.data.model_catalog import context_window_for
from copia.providers.domain.models.llm_config import LLMConfig
from copia.providers.domain.models.llm_response import LLMResponse
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_model import ProviderModel
from copia.providers.domain.models.provider_name import ProviderName
from copia.providers.domain.models.tool_definition import ToolDefinition
from copia.providers.domain.models.tool_loop_message import ToolLoopMessage
from copia.sessions.domain.models.chat_message import ChatMessage


class LLMRouter:
    """Routes a provider-agnostic request to the configured LLM provider."""

    def __init__(
        self,
        providers: dict[ProviderName, LLMProvider] | None = None,
        agent_log_store: AgentLogSink | None = None,
    ) -> None:
        load_dotenv()
        self._agent_log_store = agent_log_store
        self._providers = providers or {
            ProviderName.OPENAI: OpenAIProvider(log_store=agent_log_store),
            ProviderName.GIGACHAT: GigaChatProvider(log_store=agent_log_store),
        }

    def complete(
        self,
        messages: list[ChatMessage | ToolLoopMessage],
        config: LLMConfig,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        try:
            provider = self._providers[config.provider]
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {config.provider.value}") from error
        response = (
            provider.complete(messages, config, tools)
            if tools is not None
            else provider.complete(messages, config)
        )
        response.context_window = context_window_for(config.provider, config.model)
        return response

    def capabilities(self, provider_name: ProviderName) -> ProviderCapabilities:
        try:
            return self._providers[provider_name].capabilities
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {provider_name.value}") from error

    def models(self, provider_name: ProviderName) -> list[ProviderModel]:
        try:
            models = self._providers[provider_name].list_models()
            for model in models:
                model.context_window = context_window_for(provider_name, model.id)
            return models
        except KeyError as error:
            raise ProviderError(f"Unsupported provider: {provider_name.value}") from error
