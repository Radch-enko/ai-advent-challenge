from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from copia.agent_logs.api.models.agent_log_body_response import AgentLogBodyResponse
from copia.providers.domain.models.provider_name import ProviderName


class AgentLogExchangeResponse(BaseModel):
    id: str
    agent_turn_id: str
    operation: str
    provider: ProviderName | None = None
    model: str | None = None
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: AgentLogBodyResponse | None = None
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: AgentLogBodyResponse | None = None
    duration_seconds: float
    error: str | None = None
    created_at: datetime
