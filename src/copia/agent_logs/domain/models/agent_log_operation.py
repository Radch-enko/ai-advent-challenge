from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentLogOperation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    agent_turn_id: str
    session_id: str
    operation: Literal["user_profile_load"]
    status: Literal["completed", "failed", "skipped"]
    profile_id: str | None = None
    profile_name: str | None = None
    preference_count: int = Field(ge=0)
    applied: bool
    duration_seconds: float = Field(ge=0)
    error_code: str | None = None
    message: str | None = None
    created_at: datetime
