from __future__ import annotations

from collections.abc import Mapping

from copia.providers.data.openai_embedding_provider import OpenAIEmbeddingProvider
from copia.providers.domain.contracts.embedding_provider import EmbeddingProvider
from copia.providers.domain.errors import ProviderError
from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo


class EmbeddingRouter:
    """Resolves provider-neutral embedding operations to a registered adapter."""

    def __init__(self, providers: Mapping[str, EmbeddingProvider] | None = None) -> None:
        self._providers = (
            dict(providers) if providers is not None else {"openai": OpenAIEmbeddingProvider()}
        )

    def provider(self, provider_id: str) -> EmbeddingProvider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ProviderError(f"Unsupported embedding provider: {provider_id}") from error

    def providers(self) -> list[EmbeddingProviderInfo]:
        return sorted(
            (provider.info for provider in self._providers.values()),
            key=lambda item: item.id,
        )

    def close(self) -> None:
        for provider in self._providers.values():
            provider.close()
