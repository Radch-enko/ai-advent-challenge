from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from copia.common.domain.models.knowledge_source import KnowledgeSource
from copia.providers.domain.models.provider_name import ProviderName
from copia.tasks.domain.models.task_llm_call_status import TaskLlmCallStatus
from copia.tasks.domain.models.task_stage import TaskStage


class TaskLlmCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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
    usage: dict[str, int] | None = None
    sources: list[KnowledgeSource] = Field(default_factory=list)
