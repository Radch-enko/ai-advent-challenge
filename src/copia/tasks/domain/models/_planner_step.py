from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _PlannerStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    success_criteria: str = Field(min_length=1)
