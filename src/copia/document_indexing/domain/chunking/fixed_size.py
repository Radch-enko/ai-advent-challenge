from __future__ import annotations

from copia.document_indexing.domain.chunking.chunk_ids import create_chunk
from copia.document_indexing.domain.models.document_chunk import DocumentChunk
from copia.document_indexing.domain.models.source_document import SourceDocument
from copia.providers.domain.contracts.embedding_provider import EmbeddingProvider


class FixedSizeChunkingStrategy:
    id = "fixed-size"
    display_name = "Fixed size"
    max_tokens = 512
    overlap_tokens = 64

    def chunk(
        self,
        document: SourceDocument,
        provider: EmbeddingProvider,
        model: str,
    ) -> list[DocumentChunk]:
        text_chunks = provider.split_text(
            document.text, model, self.max_tokens, self.overlap_tokens
        )
        chunks: list[DocumentChunk] = []
        for sequence, text in enumerate(text_chunks):
            token_count = provider.count_tokens(text, model)
            if token_count > self.max_tokens:
                raise ValueError("The embedding tokenizer returned a chunk above its token limit")
            chunks.append(
                create_chunk(
                    self.id,
                    document,
                    document.title,
                    text,
                    token_count,
                    sequence,
                )
            )
        return chunks
