from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from copia.providers.domain.models.provider_name import ProviderName


class AgentLogExchange(BaseModel):
    """An immutable, transport-level provider exchange snapshot."""

    model_config = ConfigDict(frozen=True)

    id: str
    agent_turn_id: str
    session_id: str
    operation: str
    provider: ProviderName | None = None
    model: str | None = None
    method: str
    url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: bytes | None = None
    request_body_truncated: bool = False
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: bytes | None = None
    response_body_truncated: bool = False
    duration_seconds: float = Field(ge=0)
    error: str | None = None
    created_at: datetime
