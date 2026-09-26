from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from copia.mcp.domain.models.mcp_approval import McpApproval
from copia.tasks.domain.models.task_llm_call import TaskLlmCall
from copia.tasks.domain.models.task_plan import TaskPlan
from copia.tasks.domain.models.task_stage import TaskStage
from copia.tasks.domain.models.task_status import TaskStatus
from copia.tasks.domain.models.task_validation_result import TaskValidationResult


class TaskState(BaseModel):
    id: str
    original_instruction: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.RUNNING
    stage: TaskStage = TaskStage.PLANNING
    current_step: int | None = Field(default=None, ge=0)
    expected_action: str | None = None
    plan_feedback: str | None = None
    plan: TaskPlan | None = None
    validation_result: TaskValidationResult | None = None
    completion_report: str | None = None
    llm_calls: list[TaskLlmCall] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    checkpoint_revision: int = Field(default=0, ge=0)
    recovered: bool = False
    mcp_approval: McpApproval | None = None
    mcp_running_tool: str | None = None
