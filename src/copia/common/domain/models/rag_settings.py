from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RagSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k_before: int = Field(default=10, ge=1, le=100)
    similarity_threshold: float = Field(default=0.35, ge=-1, le=1)
    top_k_after: int = Field(default=3, ge=1, le=100)
    query_rewrite_enabled: bool = False
    reranker_enabled: bool = False

    @model_validator(mode="after")
    def validate_top_k_order(self) -> RagSettings:
        if self.top_k_after > self.top_k_before:
            raise ValueError("top_k_after cannot exceed top_k_before")
        return self
