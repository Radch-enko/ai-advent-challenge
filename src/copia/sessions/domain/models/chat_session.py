from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from copia.agents.domain.models.agent_config import AgentConfig
from copia.common.domain.models.rag_settings import RagSettings
from copia.sessions.domain.models.branching_context import BranchingContext
from copia.sessions.domain.models.chat_message import ChatMessage
from copia.sessions.domain.models.conversation_context import ConversationContext
from copia.tasks.domain.models.task_state import TaskState


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
    rag_enabled: bool = False
    rag_settings: RagSettings = Field(default_factory=RagSettings)
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
