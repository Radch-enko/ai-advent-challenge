from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .config import AgentConfig, ChatMessage


class ChatSession(BaseModel):
    id: str
    config: AgentConfig
    messages: list[ChatMessage] = Field(default_factory=list)
    title: str | None = None
    profile_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionSummary(BaseModel):
    id: str
    title: str | None = None
    profile_name: str | None = None
    updated_at: datetime
