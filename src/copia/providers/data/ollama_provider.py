from __future__ import annotations

import httpx

from copia.common.configuration import get_settings
from copia.providers.data.openai_provider import OpenAIProvider
from copia.providers.domain.models.provider_capabilities import ProviderCapabilities
from copia.providers.domain.models.provider_name import ProviderName


class OllamaProvider(OpenAIProvider):
    PROVIDER_NAME = ProviderName.OLLAMA
    PROVIDER_LABEL = "Ollama"
    MAX_TOKENS_PARAMETER = "max_tokens"
    INCLUDE_STREAM_USAGE = False
    SEND_PARALLEL_TOOL_CALLS = False
    capabilities = ProviderCapabilities(
        provider=ProviderName.OLLAMA,
        supported_parameters=["max_output_tokens", "temperature", "top_p"],
        supports_structured_output=True,
        supports_streaming=True,
    )

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        origin = (base_url or str(get_settings().ollama_base_url)).rstrip("/")
        self.CHAT_URL = f"{origin}/v1/chat/completions"
        self.MODELS_URL = f"{origin}/v1/models"
        self._client = client or httpx.Client(timeout=120.0)

    def _require_configuration(self) -> None:
        return None

    def _request_headers(self) -> dict[str, str]:
        return {}

    @staticmethod
    def _supports_sampling(model: str) -> bool:
        return True
