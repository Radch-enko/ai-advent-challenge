from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .config import AgentConfig, ChatMessage, ProviderName, ProviderTrace


class SummarizationEvent(BaseModel):
    id: str
    status: Literal["completed", "failed"]
    after_message_index: int = Field(ge=0)
    start_message_index: int = Field(ge=0)
    message_count: int = Field(gt=0)
    provider: ProviderName
    model: str
    duration_seconds: float = Field(ge=0)
    usage: dict[str, int] | None = None
    trace: ProviderTrace | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationContext(BaseModel):
    summary: str = ""
    summarized_message_count: int = Field(default=0, ge=0)
    events: list[SummarizationEvent] = Field(default_factory=list)


class ChatSession(BaseModel):
    id: str
    config: AgentConfig
    messages: list[ChatMessage] = Field(default_factory=list)
    context: ConversationContext = Field(default_factory=ConversationContext)
    title: str | None = None
    profile_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionSummary(BaseModel):
    id: str
    title: str | None = None
    profile_name: str | None = None
    updated_at: datetime
