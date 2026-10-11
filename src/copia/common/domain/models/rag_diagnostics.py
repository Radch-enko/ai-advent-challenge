from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from copia.common.domain.models.knowledge_source import KnowledgeSource


class RagDiagnosticCandidate(BaseModel):
    source: KnowledgeSource
    text_preview: str


class RagDiagnostics(BaseModel):
    reason: Literal["below_threshold", "citation_validation_failed"]
    similarity_threshold: float = Field(ge=-1, le=1)
    query_fallback_used: bool = False
    candidates: list[RagDiagnosticCandidate] = Field(default_factory=list)
