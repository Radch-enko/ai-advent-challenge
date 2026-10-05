from __future__ import annotations

from pydantic import BaseModel, Field

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.document_indexing.domain.models.retrieved_chunk import RetrievedChunk


class RagRetrievalResult(BaseModel):
    context_chunks: list[RetrievedChunk] = Field(default_factory=list)
    filtered_sources: list[KnowledgeSource] = Field(default_factory=list)
    rewritten_query: str | None = None

    @classmethod
    def from_single_chunk(cls, chunk: RetrievedChunk) -> RagRetrievalResult:
        return cls(context_chunks=[chunk], filtered_sources=[chunk.source])
