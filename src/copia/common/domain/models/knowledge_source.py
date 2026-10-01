from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeSource(BaseModel):
    chunk_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section: str = ""
