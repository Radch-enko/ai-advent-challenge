from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from copia.agent_logs.domain.models.agent_log_exchange import AgentLogExchange
from copia.agent_logs.domain.models.agent_log_operation import AgentLogOperation
from copia.providers.domain.models.provider_name import ProviderName


class AgentLogTurn(BaseModel):
    """A snapshot of one session turn and all provider exchanges in it."""

    model_config = ConfigDict(frozen=True)

    agent_turn_id: str
    session_id: str
    status: Literal["running", "completed", "failed"] = "running"
    provider: ProviderName | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = Field(default=0, ge=0)
    error: str | None = None
    operations: list[AgentLogOperation] = Field(default_factory=list)
    exchanges: list[AgentLogExchange] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
