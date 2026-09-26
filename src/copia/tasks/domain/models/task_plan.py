from __future__ import annotations

from pydantic import BaseModel, Field

from copia.tasks.domain.models.task_plan_step import TaskPlanStep


class TaskPlan(BaseModel):
    steps: list[TaskPlanStep] = Field(min_length=1)
