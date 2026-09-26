from __future__ import annotations

from pydantic import BaseModel, Field

from copia.providers.domain.models.tool_call import ToolCall


class ToolLoopMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant|tool|function)$")
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
