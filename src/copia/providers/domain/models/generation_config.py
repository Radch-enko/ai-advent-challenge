from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, gt=0)
