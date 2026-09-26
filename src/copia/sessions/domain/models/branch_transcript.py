from pydantic import BaseModel, Field

from copia.sessions.domain.models.chat_message import ChatMessage


class BranchTranscript(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
