from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingSettings(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)

    @classmethod
    def defaults(cls) -> EmbeddingSettings:
        return cls(provider="openai", model="text-embedding-3-small")
