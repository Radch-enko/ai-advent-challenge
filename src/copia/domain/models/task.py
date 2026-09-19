from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .config import ProviderName


class TaskStage(StrEnum):
    PLANNING = "planning"
    PLAN_REVIEW = "plan_review"
    EXECUTION = "execution"
    VALIDATION = "validation"
    REPORT = "report"
    DONE = "done"


class TaskStatus(StrEnum):
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPlanStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskLlmCallStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPlanStep(BaseModel):
    id: str
    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    success_criteria: str = Field(min_length=1)
    status: TaskPlanStepStatus = TaskPlanStepStatus.PENDING
    result: str | None = None
    error: str | None = None


class TaskPlan(BaseModel):
    steps: list[TaskPlanStep] = Field(min_length=1)


class TaskValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[str]
    checked_step_ids: list[str]
    checked_invariant_ids: list[str] = Field(default_factory=list)
    invariant_issues: list[str] = Field(default_factory=list)


class TaskLlmCall(BaseModel):
    agent_log_id: str
    stage: TaskStage
    kind: str
    step_id: str | None = None
    provider: ProviderName
    model: str
    status: TaskLlmCallStatus = TaskLlmCallStatus.RUNNING
    duration_seconds: float = Field(default=0, ge=0)
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


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


class TaskModeUpdate(BaseModel):
    enabled: bool
