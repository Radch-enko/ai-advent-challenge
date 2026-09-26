from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    created_at: datetime | None = None
    usage: dict[str, int] | None = None
    context_window: int | None = Field(default=None, gt=0)
    agent_log_id: str | None = None
    task_id: str | None = None
    task_step_id: str | None = None
