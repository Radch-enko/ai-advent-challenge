from typing import Annotated, Literal

from pydantic import BaseModel, Field

from copia.agents.domain.models.agent_config import AgentConfig
from copia.conversations.api.models.conversation_target import ConversationTarget
from copia.providers.domain.models.completion_config import CompletionConfig
from copia.sessions.domain.models.chat_message import ChatMessage


class SendMessageCommand(BaseModel):
    command: Literal["message"]
    request_id: str = Field(min_length=1, max_length=128)
    target: ConversationTarget
    content: str
    config: AgentConfig | None = None


class CompletionCommand(BaseModel):
    command: Literal["completion"]
    request_id: str = Field(min_length=1, max_length=128)
    config: CompletionConfig
    messages: list[ChatMessage]


class RetrySummarizationCommand(BaseModel):
    command: Literal["retry_summarization"]
    request_id: str = Field(min_length=1, max_length=128)
    session_id: str


class ApprovalDecisionCommand(BaseModel):
    command: Literal["approval_decision"]
    request_id: str = Field(min_length=1, max_length=128)
    conversation_id: str | None = None
    session_id: str
    approval_id: str
    decision: Literal["approve", "reject"]
    after_event_id: str | None = None


class ResumeConversationCommand(BaseModel):
    command: Literal["resume"]
    request_id: str = Field(min_length=1, max_length=128)
    conversation_id: str | None = None
    after_event_id: str | None = None


ConversationCommand = Annotated[
    SendMessageCommand
    | CompletionCommand
    | RetrySummarizationCommand
    | ApprovalDecisionCommand
    | ResumeConversationCommand,
    Field(discriminator="command"),
]
