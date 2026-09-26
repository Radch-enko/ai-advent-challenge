from __future__ import annotations

from pydantic import BaseModel, Field

from copia.tasks.domain.models.task_plan_step_status import TaskPlanStepStatus


class TaskPlanStep(BaseModel):
    id: str
    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    success_criteria: str = Field(min_length=1)
    status: TaskPlanStepStatus = TaskPlanStepStatus.PENDING
    result: str | None = None
    error: str | None = None
