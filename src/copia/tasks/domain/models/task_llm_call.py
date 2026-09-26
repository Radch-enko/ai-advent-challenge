from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from copia.providers.domain.models.provider_name import ProviderName
from copia.tasks.domain.models.task_llm_call_status import TaskLlmCallStatus
from copia.tasks.domain.models.task_stage import TaskStage


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
