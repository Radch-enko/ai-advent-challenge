from __future__ import annotations

from typing import Protocol

from copia.document_indexing.domain.models.document_chunk import DocumentChunk
from copia.document_indexing.domain.models.source_document import SourceDocument
from copia.providers.domain.contracts.embedding_provider import EmbeddingProvider


class ChunkingStrategy(Protocol):
    id: str
    display_name: str
    max_tokens: int

    def chunk(
        self,
        document: SourceDocument,
        provider: EmbeddingProvider,
        model: str,
    ) -> list[DocumentChunk]: ...
