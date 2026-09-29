from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SessionConversationTarget(BaseModel):
    kind: Literal["session"]
    id: str


class AgentConversationTarget(BaseModel):
    kind: Literal["agent"]
    id: str


ConversationTarget = Annotated[
    SessionConversationTarget | AgentConversationTarget,
    Field(discriminator="kind"),
]
