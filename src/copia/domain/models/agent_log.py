from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import ProviderName


class AgentLogContext(BaseModel):
    """Correlation data carried through one agent execution."""

    model_config = ConfigDict(frozen=True)

    agent_turn_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    operation: str = Field(default="primary", min_length=1, max_length=64)
    provider: ProviderName | None = None
    model: str | None = None


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
    exchanges: list[AgentLogExchange] = Field(default_factory=list)
