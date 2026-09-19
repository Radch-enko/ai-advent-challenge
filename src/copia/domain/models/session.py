from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import AgentConfig, ChatMessage, ProviderName, ProviderTrace
from .task import TaskState


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


class FactsUpdateEvent(BaseModel):
    id: str
    status: Literal["completed", "failed"]
    after_message_index: int = Field(ge=0)
    updates: dict[str, str] = Field(default_factory=dict)
    deletions: list[str] = Field(default_factory=list)
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
    facts_events: list[FactsUpdateEvent] = Field(default_factory=list)


class ConversationBranch(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    created_at: datetime


class ConversationCheckpoint(BaseModel):
    id: str
    source_branch_id: str
    message_count: int = Field(ge=0)
    created_at: datetime


class BranchingContext(BaseModel):
    active_branch_id: str
    branches: list[ConversationBranch]
    checkpoint: ConversationCheckpoint | None = None


class BranchTranscript(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatSession(BaseModel):
    id: str
    config: AgentConfig
    messages: list[ChatMessage] = Field(default_factory=list)
    context: ConversationContext = Field(default_factory=ConversationContext)
    branching: BranchingContext | None = None
    title: str | None = None
    profile_name: str | None = None
    user_profile_id: str | None = None
    long_term_memory_enabled: bool = False
    task_mode_enabled: bool = False
    task: TaskState | None = None
    tasks: list[TaskState] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def synchronize_task_history(self) -> ChatSession:
        if self.task is not None:
            current_index = next(
                (index for index, task in enumerate(self.tasks) if task.id == self.task.id),
                None,
            )
            if current_index is None:
                self.tasks.append(self.task)
            else:
                self.tasks[current_index] = self.task
        elif self.tasks:
            self.task = self.tasks[-1]
        return self


class ChatSessionSummary(BaseModel):
    id: str
    title: str | None = None
    profile_name: str | None = None
    updated_at: datetime
