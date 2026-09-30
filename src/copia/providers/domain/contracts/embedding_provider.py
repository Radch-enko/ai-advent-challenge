from __future__ import annotations

from typing import Protocol

from copia.providers.domain.models.embedding_provider_info import EmbeddingProviderInfo


class EmbeddingProvider(Protocol):
    info: EmbeddingProviderInfo

    @property
    def is_configured(self) -> bool: ...

    def list_models(self) -> list[str]: ...

    def count_tokens(self, text: str, model: str) -> int: ...

    def split_text(
        self, text: str, model: str, max_tokens: int, overlap_tokens: int
    ) -> list[str]: ...

    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

    def close(self) -> None: ...
