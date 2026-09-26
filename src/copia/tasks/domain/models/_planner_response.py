from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from copia.tasks.domain.models._planner_step import _PlannerStep


class _PlannerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[_PlannerStep] = Field(min_length=1, max_length=32)
