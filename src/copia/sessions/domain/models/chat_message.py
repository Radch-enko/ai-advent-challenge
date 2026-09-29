from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    created_at: datetime | None = None
    usage: dict[str, int] | None = None
    context_window: int | None = Field(default=None, gt=0)
    provider: str | None = None
    model: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    execution_status: str | None = Field(default=None, pattern="^(completed|failed)$")
    execution_error: str | None = None
    task_id: str | None = None
    task_step_id: str | None = None
