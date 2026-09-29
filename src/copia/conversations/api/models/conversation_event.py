from typing import Any, Literal

from pydantic import BaseModel

ConversationEventType = Literal[
    "conversation.started",
    "message.started",
    "message.delta",
    "tool.approval_required",
    "tool.running",
    "tool.completed",
    "approval.accepted",
    "conversation.completed",
    "conversation.failed",
]


class ConversationEvent(BaseModel):
    id: str
    event: ConversationEventType
    data: dict[str, Any]
