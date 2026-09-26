from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from copia.agent_logs.api.models.agent_log_exchange_response import AgentLogExchangeResponse
from copia.agent_logs.domain.models.agent_log_operation import AgentLogOperation
from copia.providers.domain.models.provider_name import ProviderName


class AgentLogResponse(BaseModel):
    agent_log_id: str
    agent_turn_id: str
    session_id: str
    status: Literal["running", "completed", "failed"]
    provider: ProviderName | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float
    error: str | None = None
    operations: list[AgentLogOperation] = Field(default_factory=list)
    exchanges: list[AgentLogExchangeResponse] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


AgentLogDetail = AgentLogResponse
