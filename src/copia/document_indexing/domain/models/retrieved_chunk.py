from __future__ import annotations

from pydantic import BaseModel, Field

from copia.common.domain.models.knowledge_source import KnowledgeSource


class RetrievedChunk(BaseModel):
    text: str = Field(min_length=1)
    source: KnowledgeSource
