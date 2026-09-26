from __future__ import annotations

from pydantic import BaseModel, Field

from copia.providers.domain.models.completion_config import CompletionConfig
from copia.sessions.domain.models.chat_message import ChatMessage


class CompletionRequest(BaseModel):
    config: CompletionConfig
    messages: list[ChatMessage] = Field(min_length=1)
